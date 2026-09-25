import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** Collapsible "show your working" block used next to every computed number. */
export function HowCalculated({ children, title = "How this is calculated" }: { children: ReactNode; title?: string }) {
  return (
    <details className="how">
      <summary>{title}</summary>
      <div className="how-body">
        {children}
        <p className="small muted">
          Definitions of every term: <Link to="/glossary">Glossary</Link>.
        </p>
      </div>
    </details>
  );
}

export function Formula({ children }: { children: ReactNode }) {
  return <code className="formula">{children}</code>;
}
