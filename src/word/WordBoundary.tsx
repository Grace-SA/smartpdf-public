import { Component, type ReactNode } from "react";

export class WordBoundary extends Component<
  { children: ReactNode; title?: string },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main>
        <h1>{this.props.title || "Word to PDF"}</h1>
        <p>
          This tool could not open. Reload the page to try again. Your original
          document is unchanged.
        </p>
        <button onClick={() => location.reload()}>
          Reload {this.props.title || "Word to PDF"}
        </button>
      </main>
    ) : (
      this.props.children
    );
  }
}
