import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./markdown.jsx";

function html(text) {
  return render(<Markdown text={text} />).container;
}

describe("Markdown", () => {
  it("renders headings, lists and inline styles", () => {
    const page = html("## Congés\n- **5 jours** ouvrés\n- voir `article 3`\n\n1. Demande\n2. Accord");
    expect(page.querySelector("p").textContent).toBe("Congés");
    expect(page.querySelectorAll("ul li")).toHaveLength(2);
    expect(page.querySelector("strong").textContent).toBe("5 jours");
    expect(page.querySelector("code").textContent).toBe("article 3");
    expect([...page.querySelectorAll("ol li")].map((item) => item.textContent)).toEqual(["1.Demande", "2.Accord"]);
  });

  it("keeps the line breaks of a paragraph", () => {
    const page = html("First line\nSecond line");
    expect(page.querySelectorAll("p")).toHaveLength(1);
    expect(page.querySelectorAll("br")).toHaveLength(1);
  });

  it("shows HTML from the model as text, never as markup", () => {
    const page = html('<img src=x onerror="alert(1)"> and <script>alert(2)</script>');
    expect(page.querySelector("img")).toBeNull();
    expect(page.querySelector("script")).toBeNull();
    expect(page.textContent).toContain("<img src=x");
  });
});
