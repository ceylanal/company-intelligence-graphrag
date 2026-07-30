"use client";

import { defaultUrlTransform } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

interface MarkdownAnswerProps {
  answer: string;
  citationIndexes: Set<number>;
  onCitation: (index: number) => void;
}

function linkCitations(markdown: string): string {
  return markdown.replace(/\[Source\s+(\d+)]/gi, "[$&](#citation-$1)");
}

export function MarkdownAnswer({ answer, citationIndexes, onCitation }: MarkdownAnswerProps) {
  return (
    <div className="markdown" data-testid="answer-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        urlTransform={(url) => (url.startsWith("#citation-") ? url : defaultUrlTransform(url))}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#citation-")) {
              const index = Number(href.slice("#citation-".length));
              const available = Number.isInteger(index) && citationIndexes.has(index);
              return available ? (
                <button
                  className="citation-link"
                  type="button"
                  aria-label={`Open source ${index}`}
                  onClick={() => onCitation(index)}
                >
                  {children}
                </button>
              ) : (
                <span className="citation-missing" title="Citation metadata unavailable">
                  {children}
                </span>
              );
            }
            const safeExternal = href?.startsWith("http://") || href?.startsWith("https://");
            return (
              <a
                href={href}
                target={safeExternal ? "_blank" : undefined}
                rel={safeExternal ? "noopener noreferrer" : undefined}
              >
                {children}
              </a>
            );
          },
          table: ({ children }) => (
            <div className="table-scroll" tabIndex={0} aria-label="Scrollable data table">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {linkCitations(answer)}
      </ReactMarkdown>
    </div>
  );
}
