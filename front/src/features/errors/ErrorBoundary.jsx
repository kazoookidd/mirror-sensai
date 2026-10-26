import { Component } from "react";
import { EmptyState } from "../../components/feedback/EmptyState/EmptyState.jsx";
import { Button } from "../../components/ui/Button/Button.jsx";
import styles from "./ErrorBoundary.module.css";

export class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidUpdate(previous) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) this.setState({ failed: false });
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className={styles.screen} role="alert">
        <EmptyState icon="alert" iconSize={16} title="Something went wrong">
          This screen hit an unexpected error. Your chats are saved: reload the page to continue.
        </EmptyState>
        <Button variant="primary" icon="refresh" onClick={() => window.location.reload()}>Reload</Button>
      </div>
    );
  }
}
