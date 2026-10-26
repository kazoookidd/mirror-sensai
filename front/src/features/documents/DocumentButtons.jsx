import { Button } from "../../components/ui/Button/Button.jsx";
import { TestTag } from "../../components/feedback/TestTag/TestTag.jsx";

const TEST_HINT = "[TEST] Not available yet";

export function ImportButton({ className }) {
  return (
    <Button variant="primary" icon="upload" disabled title={TEST_HINT} className={className}>
      Import a document <TestTag />
    </Button>
  );
}

export function QueryButton({ label }) {
  return <Button icon="message" disabled title={TEST_HINT}>{label} <TestTag /></Button>;
}
