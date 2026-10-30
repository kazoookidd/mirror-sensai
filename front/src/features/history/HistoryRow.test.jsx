import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { HistoryRow } from "./HistoryRow.jsx";

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };
const conversation = (model) => ({ id: 3, title: "Congés", preview: "4 jours.", updated_at: "2026-10-29 10:00:00", model });
const renderRow = (model) => render(
  <MemoryRouter future={FUTURE}><ul><HistoryRow conversation={conversation(model)} actions={{}} /></ul></MemoryRouter>);

describe("HistoryRow", () => {
  afterEach(cleanup);

  it("shows the model of the last answer", () => {
    renderRow("qwen2.5:3b");
    expect(screen.getByTitle("Last answer written by qwen2.5:3b").textContent).toBe("qwen2.5:3b");
  });

  it("shows a dash before any answer from a model", () => {
    renderRow(null);
    expect(screen.getByTitle("No answer from a model yet").textContent).toBe("-");
  });
});
