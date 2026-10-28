import { Button } from "../../components/ui/Button/Button.jsx";
import { TestTag } from "../../components/feedback/TestTag/TestTag.jsx";

const TEST_HINT = "[TEST] Not available yet";

export function ImportButton({ importing, onClick, className }) {
  return (
    <Button variant="primary" icon="upload" disabled={Boolean(importing)} onClick={onClick} className={className}>
      {importing ? "Importing..." : "Import a document"}
    </Button>
  );
}

export function QueryButton({ label }) {
  return <Button icon="message" disabled title={TEST_HINT}>{label} <TestTag /></Button>;
}
