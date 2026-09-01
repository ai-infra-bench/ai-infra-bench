import taskData from '@/app/generated/tasks.json';

export type BenchmarkTask = {
  slug: string;
  name: string;
  version: string | null;
  description: string;
  keywords: string[];
  track: string | null;
  workloadType: string | null;
  subsystems: string[];
  repository: string | null;
  baseCommit: string | null;
  dependencyCutoff: string | null;
  publicationState: string | null;
  agentTimeoutSec: number | null;
  accelerator: string | null;
  cpus: number | null;
  memoryMb: number | null;
  networkMode: string | null;
  verifierTimeoutSec: number | null;
  instructionHtml: string;
  verifierFiles: Array<{
    name: string;
    highlightedHtml: string;
    lineCount: number;
  }>;
  solutionFiles: Array<{
    name: string;
    highlightedHtml: string;
    lineCount: number;
  }>;
};

export const tasks = taskData as BenchmarkTask[];
