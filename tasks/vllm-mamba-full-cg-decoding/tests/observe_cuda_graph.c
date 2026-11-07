/* SPDX-License-Identifier: Apache-2.0
 * External CUDA graph observer for Linux x86-64.
 *
 * Runs as the same unprivileged UID as the tracee, with dumpability disabled.
 * The tracee cannot open the observer's private report pipe or modify its
 * memory. Hardware execution breakpoints observe the root-owned CUDA driver,
 * outside candidate Python. SIGUSR1/SIGUSR2 delimit inference after warmup.
 * Candidate stdout goes to stderr; only this process writes the JSON report.
 */
#define _GNU_SOURCE
#include <sys/ptrace.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/prctl.h>
#include <sys/user.h>
#include <sys/stat.h>
#include <elf.h>
#include <stddef.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
struct thread {
    pid_t id;
    int live, stopped, sig;
    unsigned long returns[16];
    int active[16], depth;
}
threads[2048];
int nt=0, arming=0, armed=0, finished=0, child_exit=-1;
unsigned long addresses[4];
int naddr=0;
unsigned long long hits=0, failed=0;
void fail(const char *s) {
    perror(s);
    exit(120);
}
struct thread *track(pid_t id) {
    for(int i=0; i<nt; i++)if(threads[i].id==id)return &threads[i];
    if(nt>=2048) {
        errno=EOVERFLOW;
        fail("threads");
    }
    threads[nt]=(struct thread) {
        .id=id, .live=1
    };
    return &threads[nt++];
}
void request(enum __ptrace_request req,pid_t pid,void *addr,void *value) {
    if(ptrace(req,pid,addr,value)==-1)fail("ptrace");
}
void resume(struct thread *t) {
    request(PTRACE_CONT,t->id,0,(void *)(long)t->sig);
    t->stopped=0;
    t->sig=0;
}
void resolve(pid_t pid) {
    char maps[64],line[8192],path[4096]="";
    unsigned long base=0,start,end,off;
    snprintf(maps,sizeof(maps),"/proc/%d/maps",pid);
    FILE *f=fopen(maps,"r");
    if(!f)fail("maps");
    while(fgets(line,sizeof(line),f)) {
        char perms[8],p[4096];
        if(sscanf(line,"%lx-%lx %7s %lx %*s %*s %4095s",&start,&end,perms,&off,p)==5 && strstr(p,"/libcuda.so.") && off==0) {
            base=start;
            strcpy(path,p);
            break;
        }
    }
    fclose(f);
    if(!base) {
        errno=ENOENT;
        fail("libcuda not loaded");
    }
    int fd=open(path,O_RDONLY|O_NOFOLLOW);
    struct stat st;
    if(fd<0||fstat(fd,&st)||st.st_uid!=0||(st.st_mode&022)) {
        errno=EPERM;
        fail("untrusted CUDA driver");
    }
    char *data=malloc(st.st_size);
    if(!data||read(fd,data,st.st_size)!=(ssize_t)st.st_size)fail("read ELF");
    close(fd);
    Elf64_Ehdr *eh=(Elf64_Ehdr*)data;
    if(memcmp(eh->e_ident,ELFMAG,SELFMAG)||eh->e_ident[EI_CLASS]!=ELFCLASS64) {
        errno=EINVAL;
        fail("ELF class");
    }
    Elf64_Shdr *sections=(Elf64_Shdr*)(data+eh->e_shoff);
    for(int i=0; i<eh->e_shnum; i++)if(sections[i].sh_type==SHT_DYNSYM) {
        Elf64_Sym *syms=(Elf64_Sym*)(data+sections[i].sh_offset);
        char *strings=data+sections[sections[i].sh_link].sh_offset;
        int n=sections[i].sh_size/sizeof(*syms);
        for(int j=0; j<n; j++) {
            char *name=strings+syms[j].st_name;
            if(!strcmp(name,"cuGraphLaunch")||!strcmp(name,"cuGraphLaunch_ptsz")) {
                unsigned long a=base+syms[j].st_value;
                int dup=0;
                for(int k=0; k<naddr; k++)dup|=addresses[k]==a;
                if(!dup&&naddr<4) {
                    addresses[naddr++]=a;
                    fprintf(stderr,"observer symbol %s %lx\n",name,a);
                }
            }
        }
    }
    free(data);
    if(!naddr) {
        errno=ENOENT;
        fail("CUDA graph symbol");
    }
}
void debugregs(pid_t id) {
    unsigned long flags=0;
    for(int i=0; i<naddr; i++) {
        request(PTRACE_POKEUSER,id,(void*)offsetof(struct user,u_debugreg[i]),(void*)addresses[i]);
        flags|=1ul<<(2*i);
    }
    request(PTRACE_POKEUSER,id,(void*)offsetof(struct user,u_debugreg[6]),0);
    request(PTRACE_POKEUSER,id,(void*)offsetof(struct user,u_debugreg[7]),(void*)flags);
}
int main(int argc,char **argv) {
    if(argc<2)return 2;
    if(prctl(PR_SET_DUMPABLE,0))fail("protect observer");
    int ready[2],go[2];
    if(pipe(ready)||pipe(go))fail("pipe");
    pid_t child=fork();
    if(child<0)fail("fork");
    if(!child) {
        close(ready[0]);
        close(go[1]);
        prctl(PR_SET_DUMPABLE,1);
        if(write(ready[1],"r",1)!=1)_exit(121);
        close(ready[1]);
        char c;
        if(read(go[0],&c,1)!=1)_exit(121);
        close(go[0]);
        dup2(STDERR_FILENO,STDOUT_FILENO);
        execvp(argv[1],argv+1);
        _exit(127);
    }
    close(ready[1]);
    close(go[0]);
    char c;
    if(read(ready[0],&c,1)!=1)fail("ready");
    close(ready[0]);
    unsigned long options=PTRACE_O_TRACECLONE|PTRACE_O_TRACEFORK|PTRACE_O_TRACEVFORK|PTRACE_O_TRACEEXEC|PTRACE_O_EXITKILL;
    request(PTRACE_SEIZE,child,0,(void*)options);
    track(child);
    if(write(go[1],"g",1)!=1)fail("release");
    close(go[1]);
    for(; ; ) {
        int status;
        pid_t tid=waitpid(-1,&status,__WALL);
        if(tid<0) {
            if(errno==EINTR)continue;
            if(errno==ECHILD)break;
            fail("wait");
        }
        struct thread *t=track(tid);
        if(WIFEXITED(status)||WIFSIGNALED(status)) {
            t->live=0;
            if(tid==child)child_exit=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
            continue;
        }
        if(!WIFSTOPPED(status))continue;
        t->stopped=1;
        int sig=WSTOPSIG(status),event=status>>16;
        t->sig=0;
        if(event==PTRACE_EVENT_CLONE||event==PTRACE_EVENT_FORK||event==PTRACE_EVENT_VFORK) {
            unsigned long id=0;
            request(PTRACE_GETEVENTMSG,tid,0,&id);
            track(id);
        }
        if(!event&&sig==SIGUSR1&&!armed) {
            arming=1;
            for(int i=0; i<nt; i++)if(threads[i].live&&!threads[i].stopped) {
                if(ptrace(PTRACE_INTERRUPT,threads[i].id,0,0)==-1&&errno!=ESRCH)fail("pause");
            }
        }
        else if(!event&&sig==SIGUSR2&&armed) {
            finished=1;
        }
        else if(!event&&sig==SIGTRAP&&armed) {
            struct user_regs_struct regs;
            request(PTRACE_GETREGS,tid,0,&regs);
            int entry=0, handled=0;
            for(int i=0; i<naddr; i++) entry|=regs.rip==addresses[i];
            if(entry) {
                if(t->depth>=16) {
                    errno=EOVERFLOW;
                    fail("nested graph API calls");
                }
                errno=0;
                long ret=ptrace(PTRACE_PEEKDATA,tid,(void*)regs.rsp,0);
                if(ret==-1&&errno) fail("CUDA return address");
                t->returns[t->depth]=(unsigned long)ret;
                t->active[t->depth]=!finished;
                t->depth++;
                handled=1;
            }
            else if(t->depth&&regs.rip==t->returns[t->depth-1]) {
                t->depth--;
                if(t->active[t->depth]) {
                    if((unsigned int)regs.rax==0) hits++;
                    else failed++;
                }
                handled=1;
            }
            if(handled) {
                unsigned long flags=0;
                for(int i=0; i<naddr; i++) flags|=1ul<<(2*i);
                unsigned long ret=t->depth?t->returns[t->depth-1]:0;
                if(t->depth) flags|=1ul<<4;
                request(PTRACE_POKEUSER,tid,(void*)offsetof(struct user,u_debugreg[2]),(void*)ret);
                request(PTRACE_POKEUSER,tid,(void*)offsetof(struct user,u_debugreg[7]),(void*)flags);
                request(PTRACE_POKEUSER,tid,(void*)offsetof(struct user,u_debugreg[6]),0);
                regs.eflags|=1<<16;
                request(PTRACE_SETREGS,tid,0,&regs);
            }
            else t->sig=SIGTRAP;
        }
        else if(!event&&sig!=SIGTRAP&&sig!=SIGSTOP)t->sig=sig;
        if(arming) {
            int all=1;
            for(int i=0; i<nt; i++)if(threads[i].live&&!threads[i].stopped)all=0;
            if(all) {
                resolve(child);
                for(int i=0; i<nt; i++)if(threads[i].live)debugregs(threads[i].id);
                armed=1;
                arming=0;
                for(int i=0; i<nt; i++)if(threads[i].live)resume(&threads[i]);
            }
        }
        else {
            if(armed&&event==PTRACE_EVENT_STOP)debugregs(tid);
            resume(t);
        }
    }
    printf("{\"child_exit\":%d,\"armed\":%d,\"finished\":%d,\"graph_launches\":%llu,\"failed_graph_launches\":%llu}\n",child_exit,armed,finished,hits,failed);
    return child_exit==0&&armed&&finished?0:1;
}
