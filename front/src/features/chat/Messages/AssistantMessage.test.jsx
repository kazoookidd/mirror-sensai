import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AssistantMessage } from "./AssistantMessage.jsx";

const SOURCES = [
  { source: "loi_conge_mariage_pacs.md", page: null, score: 0.712, semantic: 0.69, keyword: 0.83, excerpt: "Quatre jours pour un mariage." },
  { source: "accord.pdf", page: 4, score: 0.61, semantic: 0.6, keyword: 0.66, excerpt: "Article 4." },
];

describe("AssistantMessage sources [R2]", () => {
  afterEach(cleanup);

  it("opens the passages the answer comes from, with their page and score", () => {
    render(<AssistantMessage text="Quatre jours." sources={SOURCES} showSources />);
    fireEvent.click(screen.getByRole("button", { name: "View sources · 2" }));
    const list = screen.getByRole("list", { name: "Sources of the answer" });
    expect(list.textContent).toContain("loi_conge_mariage_pacs.md");
    expect(list.textContent).toContain("accord.pdf, p. 4");
    expect(screen.getByText("71 %").getAttribute("title")).toBe("Relevance 0.71: meaning 0.69, keywords 0.83");
    fireEvent.click(screen.getByRole("button", { name: "Hide sources" }));
    expect(screen.queryByRole("list", { name: "Sources of the answer" })).toBeNull();
  });

  it("shows no sources button when they are turned off, absent, or on a shared page", () => {
    const { rerender } = render(<AssistantMessage text="Oui." sources={SOURCES} showSources={false} />);
    expect(screen.queryByRole("button", { name: /View sources/ })).toBeNull();
    rerender(<AssistantMessage text="Oui." showSources />);
    expect(screen.queryByRole("button", { name: /View sources/ })).toBeNull();
    rerender(<AssistantMessage text="Oui." sources={SOURCES} showSources readOnly />);
    expect(screen.queryByRole("button", { name: /View sources/ })).toBeNull();
  });
});
