import taskIndex from '@/app/generated/task-index.json';
import { taskLoaders } from '@/app/generated/task-loaders';

export type ManifestValue = string | number | boolean | string[] | number[] | null;
export type ManifestSection = Record<string, ManifestValue>;

export type SourceFileRecord = {
  name: string;
  lineCount: number;
  url: string;
};

export type TaskSummary = {
  slug: string;
  name: string;
  version: string | null;
  description: string;
  keywords: string[];
  track: string | null;
  workloadType: string | null;
  subsystems: string[];
  repository: string | null;
  accelerator: string | null;
};

export type BenchmarkTask = TaskSummary & {
  baseCommit: string | null;
  dependencyCutoff: string | null;
  publicationState: string | null;
  agentTimeoutSec: number | null;
  cpus: number | null;
  memoryMb: number | null;
  networkMode: string | null;
  verifierTimeoutSec: number | null;
  manifest: {
    schemaVersion: ManifestValue;
    taskVersion: ManifestValue;
    metadata: ManifestSection;
    agent: ManifestSection;
    environment: ManifestSection;
    verifier: ManifestSection;
  };
  instructionHtml: string;
  verifierFiles: SourceFileRecord[];
  solutionFiles: SourceFileRecord[];
  environmentFiles: SourceFileRecord[];
};

export const tasks = taskIndex as TaskSummary[];

export async function getTask(slug: string): Promise<BenchmarkTask | null> {
  const loader = taskLoaders[slug as keyof typeof taskLoaders];
  if (!loader) return null;
  const taskModule = await loader();
  return taskModule.default as BenchmarkTask;
}
