const fs=require('node:fs'); const dir=fs.mkdtempSync('/tmp/pi-file-revision-'); const p=dir+'/probe'; let equal=0;
for(let i=0;i<100;i++){fs.writeFileSync(p,'old'); const a=fs.statSync(p,{bigint:true}); fs.writeFileSync(p,'new'); const b=fs.statSync(p,{bigint:true}); if(a.mtimeNs===b.mtimeNs&&a.ctimeNs===b.ctimeNs)equal++;}
fs.rmSync(dir,{recursive:true}); console.log(JSON.stringify({sameRevisionWrites:equal,total:100,uid:process.getuid()}));
