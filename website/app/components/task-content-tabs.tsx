'use client';

import { useEffect, useRef, useState } from 'react';
import * as Select from '@radix-ui/react-select';
import * as Tabs from '@radix-ui/react-tabs';
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from '@radix-ui/react-icons';

type SourceFile = {
  name: string;
  highlightedHtml: string;
  lineCount: number;
};

type EnvironmentFact = [label: string, value: string];

export function TaskContentTabs({
  instructionHtml,
  verifierFiles,
  solutionFiles,
  environmentFiles,
  metadata,
}: {
  instructionHtml: string;
  verifierFiles: SourceFile[];
  solutionFiles: SourceFile[];
  environmentFiles: SourceFile[];
  metadata: EnvironmentFact[];
}) {
  const [activeVerifier, setActiveVerifier] = useState(0);
  const [activeOracle, setActiveOracle] = useState(0);
  const [activeEnvironment, setActiveEnvironment] = useState(0);
  const [wrapLines, setWrapLines] = useState(false);

  return (
    <Tabs.Root className="task-content" defaultValue="instruction">
      <Tabs.List className="content-tabs" aria-label="Task content">
        <Tabs.Trigger className="content-tab" value="instruction">
          Instruction
        </Tabs.Trigger>
        <Tabs.Trigger className="content-tab" value="verifier">
          Verifier
        </Tabs.Trigger>
        <Tabs.Trigger className="content-tab" value="oracle">
          Oracle
        </Tabs.Trigger>
        <Tabs.Trigger className="content-tab" value="environment">
          Environment
        </Tabs.Trigger>
        <Tabs.Trigger className="content-tab" value="metadata">
          Metadata
        </Tabs.Trigger>
      </Tabs.List>

      <Tabs.Content className="content-panel instruction-panel" value="instruction">
        <div className="markdown-body" dangerouslySetInnerHTML={{ __html: instructionHtml }} />
      </Tabs.Content>

      <Tabs.Content className="content-panel" value="verifier">
        <SourceDocument
          directory="tests"
          files={verifierFiles}
          activeFile={activeVerifier}
          onFileChange={setActiveVerifier}
          wrapLines={wrapLines}
          onWrapLinesChange={setWrapLines}
          fallback="No verifier files are available."
        />
      </Tabs.Content>

      <Tabs.Content className="content-panel" value="oracle">
        <SourceDocument
          directory="solution"
          files={solutionFiles}
          activeFile={activeOracle}
          onFileChange={setActiveOracle}
          wrapLines={wrapLines}
          onWrapLinesChange={setWrapLines}
          fallback="No oracle files are available."
        />
      </Tabs.Content>

      <Tabs.Content className="content-panel" value="environment">
        <SourceDocument
          directory="environment"
          files={environmentFiles}
          activeFile={activeEnvironment}
          onFileChange={setActiveEnvironment}
          wrapLines={wrapLines}
          onWrapLinesChange={setWrapLines}
          fallback="No environment files are available."
        />
      </Tabs.Content>

      <Tabs.Content className="content-panel environment-panel" value="metadata">
        <dl className="environment-list">
          {metadata.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </Tabs.Content>
    </Tabs.Root>
  );
}

function SourceDocument({
  directory,
  files,
  activeFile,
  onFileChange,
  wrapLines,
  onWrapLinesChange,
  fallback,
}: {
  directory: string;
  files: SourceFile[];
  activeFile: number;
  onFileChange: (index: number) => void;
  wrapLines: boolean;
  onWrapLinesChange: (wrap: boolean) => void;
  fallback: string;
}) {
  const sourceRef = useRef<HTMLDivElement>(null);
  const selectedFile = files[activeFile];

  useEffect(() => {
    sourceRef.current?.scrollTo({ top: 0, left: 0 });
  }, [selectedFile?.name]);

  return (
    <div className="source-document">
      <header className="source-toolbar">
        {selectedFile ? (
          <Select.Root value={String(activeFile)} onValueChange={(value) => onFileChange(Number(value))}>
            <Select.Trigger className="source-file-trigger" aria-label={`Select ${directory} file`}>
              <span className="source-directory">{directory}/</span>
              <Select.Value />
              <Select.Icon className="source-file-icon">
                <ChevronDownIcon />
              </Select.Icon>
            </Select.Trigger>
            <Select.Portal>
              <Select.Content
                className="source-select-content"
                position="popper"
                sideOffset={6}
                align="start"
              >
                <Select.ScrollUpButton className="source-select-scroll">
                  <ChevronUpIcon />
                </Select.ScrollUpButton>
                <Select.Viewport className="source-select-viewport">
                  {files.map((file, index) => (
                    <Select.Item className="source-select-item" value={String(index)} key={file.name}>
                      <Select.ItemText>{file.name}</Select.ItemText>
                      <Select.ItemIndicator className="source-select-indicator">
                        <CheckIcon />
                      </Select.ItemIndicator>
                    </Select.Item>
                  ))}
                </Select.Viewport>
                <Select.ScrollDownButton className="source-select-scroll">
                  <ChevronDownIcon />
                </Select.ScrollDownButton>
              </Select.Content>
            </Select.Portal>
          </Select.Root>
        ) : (
          <code>{directory}/</code>
        )}

        <div className="source-actions">
          <span>
            {selectedFile?.lineCount ?? 0}{' '}
            {(selectedFile?.lineCount ?? 0) === 1 ? 'line' : 'lines'}
          </span>
          <button
            type="button"
            aria-pressed={wrapLines}
            onClick={() => onWrapLinesChange(!wrapLines)}
          >
            Wrap lines
          </button>
        </div>
      </header>

      {selectedFile ? (
        <div
          ref={sourceRef}
          className={`source-code${wrapLines ? ' is-wrapped' : ''}`}
          aria-label={`${directory}/${selectedFile.name}`}
          tabIndex={0}
          dangerouslySetInnerHTML={{ __html: selectedFile.highlightedHtml }}
        />
      ) : (
        <pre className="source-fallback"><code>{fallback}</code></pre>
      )}
    </div>
  );
}
