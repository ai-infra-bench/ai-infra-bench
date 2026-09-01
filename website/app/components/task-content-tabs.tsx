'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type VerifierFile = {
  name: string;
  highlightedHtml: string;
  lineCount: number;
};
type ContentTab = 'instruction' | 'verifier' | 'oracle';

export function TaskContentTabs({
  instruction,
  verifierFiles,
  solutionFiles,
}: {
  instruction: string;
  verifierFiles: VerifierFile[];
  solutionFiles: VerifierFile[];
}) {
  const [activeTab, setActiveTab] = useState<ContentTab>('instruction');
  const [activeVerifier, setActiveVerifier] = useState(0);
  const [activeOracle, setActiveOracle] = useState(0);
  const [wrapLines, setWrapLines] = useState(false);
  const selectedVerifier = verifierFiles[activeVerifier];
  const selectedOracle = solutionFiles[activeOracle];

  return (
    <section className="task-content" aria-label="Task files">
      <div className="content-tabs" role="tablist" aria-label="Task content">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'instruction'}
          onClick={() => setActiveTab('instruction')}
        >
          Instruction
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'verifier'}
          onClick={() => setActiveTab('verifier')}
        >
          Verifier
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'oracle'}
          onClick={() => setActiveTab('oracle')}
        >
          Oracle
        </button>
      </div>

      <div className="content-panel" role="tabpanel">
        {activeTab === 'instruction' && (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{instruction}</ReactMarkdown>
          </div>
        )}

        {activeTab === 'verifier' && (
          <SourceDocument
            name={selectedVerifier ? `tests/${selectedVerifier.name}` : 'tests/'}
            lineCount={selectedVerifier?.lineCount ?? 0}
            html={selectedVerifier?.highlightedHtml}
            fallback="No verifier files are available."
            wrapLines={wrapLines}
            onWrapLinesChange={setWrapLines}
            files={verifierFiles.map((file) => file.name)}
            activeFile={activeVerifier}
            onFileChange={setActiveVerifier}
            directory="tests"
          />
        )}

        {activeTab === 'oracle' && (
          <SourceDocument
            name={selectedOracle ? `solution/${selectedOracle.name}` : 'solution/'}
            lineCount={selectedOracle?.lineCount ?? 0}
            html={selectedOracle?.highlightedHtml}
            fallback="No oracle files are available."
            wrapLines={wrapLines}
            onWrapLinesChange={setWrapLines}
            files={solutionFiles.map((file) => file.name)}
            activeFile={activeOracle}
            onFileChange={setActiveOracle}
            directory="solution"
          />
        )}
      </div>
    </section>
  );
}

function SourceDocument({
  name,
  lineCount,
  html,
  fallback,
  wrapLines,
  onWrapLinesChange,
  files,
  activeFile,
  onFileChange,
  directory,
}: {
  name: string;
  lineCount: number;
  html?: string;
  fallback: string;
  wrapLines: boolean;
  onWrapLinesChange: (wrap: boolean) => void;
  files?: string[];
  activeFile?: number;
  onFileChange?: (index: number) => void;
  directory?: string;
}) {
  return (
    <div className="source-document">
      <header>
        {files && activeFile !== undefined && onFileChange ? (
          <details className="source-file-picker">
            <summary>
              <span>{directory}/</span>
              <span className="source-file-name">{files[activeFile]}</span>
              <span className="source-file-chevron" aria-hidden="true">⌄</span>
            </summary>
            <div className="source-file-menu" aria-label={`${directory ?? 'Source'} files`}>
              {files.map((file, index) => (
                <button
                  type="button"
                  aria-current={activeFile === index ? 'page' : undefined}
                  onClick={(event) => {
                    onFileChange(index);
                    event.currentTarget.closest('details')?.removeAttribute('open');
                  }}
                  key={file}
                >
                  {file}
                </button>
              ))}
            </div>
          </details>
        ) : (
          <code>{name}</code>
        )}
        <div className="source-actions">
          <span>{lineCount} {lineCount === 1 ? 'line' : 'lines'}</span>
          <button
            type="button"
            aria-pressed={wrapLines}
            onClick={() => onWrapLinesChange(!wrapLines)}
          >
            Wrap lines
          </button>
        </div>
      </header>
      {html ? (
        <div
          className={`source-code${wrapLines ? ' is-wrapped' : ''}`}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre className="source-fallback"><code>{fallback}</code></pre>
      )}
    </div>
  );
}
