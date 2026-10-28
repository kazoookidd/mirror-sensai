import { useRef, useState } from "react";
import { documents } from "../../api/documents.js";

export const ACCEPTED = ".pdf,.txt,.md";

export function useImport(onImported) {
  const [importing, setImporting] = useState(null);
  const [results, setResults] = useState([]);
  const input = useRef(null);

  const importFiles = async (files) => {
    if (!files.length || importing) return;
    setResults([]);
    for (const file of files) {
      setImporting(file.name);
      try {
        const { document } = await documents.upload(file);
        setResults((list) => [...list, { name: file.name, ok: true, chunks: document.chunks }]);
      } catch (failure) {
        setResults((list) => [...list, { name: file.name, ok: false, error: failure.message }]);
      }
      onImported();
    }
    setImporting(null);
  };

  const inputProps = {
    ref: input, type: "file", accept: ACCEPTED, multiple: true, hidden: true,
    onChange: (event) => { importFiles([...event.target.files]); event.target.value = ""; },
  };
  return { importing, results, importFiles, open: () => input.current.click(), inputProps };
}
