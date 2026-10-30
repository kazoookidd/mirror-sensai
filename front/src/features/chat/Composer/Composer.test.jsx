import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useApp } from "../../../context/AppContext.jsx";
import { Composer } from "./Composer.jsx";

vi.mock("../../../context/AppContext.jsx", () => ({ useApp: vi.fn() }));
vi.mock("./ContextGauge.jsx", () => ({ ContextGauge: () => null }));

function renderComposer(hrDocuments, busy = false) {
  const switchHrDocuments = vi.fn().mockResolvedValue();
  useApp.mockReturnValue({ ollama: { online: true }, hrDocuments, switchHrDocuments });
  render(<Composer onSend={vi.fn()} onStop={vi.fn()} busy={busy} onAttach={vi.fn()} />);
  return { switchHrDocuments, button: screen.getByRole("button", { name: /HR documents/ }) };
}

describe("Composer HR documents switch [R1]", () => {
  afterEach(cleanup);

  it("turns the HR documents off and on", () => {
    const on = renderComposer(true);
    expect(on.button.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(on.button);
    expect(on.switchHrDocuments).toHaveBeenCalledWith(false);
    cleanup();
    const off = renderComposer(false);
    expect(off.button.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(off.button);
    expect(off.switchHrDocuments).toHaveBeenCalledWith(true);
  });

  it("cannot be changed while an answer is written", () => {
    expect(renderComposer(true, true).button.disabled).toBe(true);
  });
});
