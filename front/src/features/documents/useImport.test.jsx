import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { documents } from "../../api/documents.js";
import { useImport } from "./useImport.js";

vi.mock("../../api/documents.js", () => ({ documents: { upload: vi.fn() } }));

const file = (name) => new File(["text"], name);

describe("useImport", () => {
  beforeEach(() => vi.clearAllMocks());

  it("imports the files one after the other and reports each one", async () => {
    documents.upload
      .mockResolvedValueOnce({ document: { chunks: 3 } })
      .mockRejectedValueOnce(new Error("Unsupported file type: use .md, .pdf, .txt."));
    const onImported = vi.fn();
    const { result } = renderHook(() => useImport(onImported));
    await act(() => result.current.importFiles([file("leave.md"), file("photo.png")]));
    expect(documents.upload.mock.calls.map(([sent]) => sent.name)).toEqual(["leave.md", "photo.png"]);
    expect(result.current.results).toEqual([
      { name: "leave.md", ok: true, chunks: 3 },
      { name: "photo.png", ok: false, error: "Unsupported file type: use .md, .pdf, .txt." },
    ]);
    expect(onImported).toHaveBeenCalledTimes(2);
    expect(result.current.importing).toBeNull();
  });

  it("only accepts the formats the base can read", () => {
    const { result } = renderHook(() => useImport(vi.fn()));
    expect(result.current.inputProps.accept).toBe(".pdf,.txt,.md");
    expect(result.current.inputProps.multiple).toBe(true);
  });
});
