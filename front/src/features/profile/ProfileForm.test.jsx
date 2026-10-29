import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { profile as profileApi } from "../../api/profile.js";
import { contextText } from "./ContextPreview.jsx";
import { ProfileForm } from "./ProfileForm.jsx";

vi.mock("../../api/profile.js", () => ({ profile: { get: vi.fn(), save: vi.fn() } }));

const EMPTY = { name: "", role: "", department: "", language: "", tone: "", instructions: "" };
const SOPHIE = { name: "Sophie Martin", role: "Consultante", department: "Engineering", language: "French",
  tone: "concise", instructions: "Cite toujours l'article." };

const save = () => screen.getByRole("button", { name: "Save" });

describe("ProfileForm", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("shows the saved profile, and Save only once something changed", async () => {
    profileApi.get.mockResolvedValue({ profile: SOPHIE, context: "" });
    render(<ProfileForm onCancel={() => {}} />);
    expect(await screen.findByDisplayValue("Consultante")).toBeTruthy();
    expect(save().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Job title"), { target: { value: "Manager" } });
    expect(save().disabled).toBe(false);
  });

  it("saves the whole profile and shows what the server kept", async () => {
    profileApi.get.mockResolvedValue({ profile: EMPTY, context: "" });
    profileApi.save.mockResolvedValue({ profile: { ...EMPTY, role: "RH" }, context: "[profile]\njob: RH" });
    render(<ProfileForm onCancel={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Job title"), { target: { value: "  RH  " } });
    fireEvent.click(save());
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(profileApi.save).toHaveBeenCalledWith({ ...EMPTY, role: "  RH  " });
    expect(screen.getByLabelText("Job title").value).toBe("RH");
    expect(save().disabled).toBe(true);
  });

  it("shows the reason of a refusal and keeps what was typed", async () => {
    profileApi.get.mockResolvedValue({ profile: EMPTY, context: "" });
    profileApi.save.mockRejectedValue(new Error("name is too long."));
    render(<ProfileForm onCancel={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Full name"), { target: { value: "Sophie" } });
    fireEvent.click(save());
    expect((await screen.findByRole("alert")).textContent).toBe("name is too long.");
    expect(screen.getByLabelText("Full name").value).toBe("Sophie");
  });

  it("shows the account type, which cannot be edited", async () => {
    profileApi.get.mockResolvedValue({ profile: EMPTY, context: "", account: { role: "employee", label: "Employee" } });
    render(<ProfileForm onCancel={() => {}} />);
    expect(await screen.findByText("Employee")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: /account/i })).toBeNull();
    expect(screen.queryByRole("combobox", { name: /account/i })).toBeNull();
  });

  it("keeps a department typed in the CLI selectable", async () => {
    profileApi.get.mockResolvedValue({ profile: { ...EMPTY, department: "Paie" }, context: "" });
    render(<ProfileForm onCancel={() => {}} />);
    expect((await screen.findByLabelText("Department")).value).toBe("Paie");
  });
});

describe("contextText", () => {
  it("is the text the backend gives the model (context_text in back/Memories/Profile.py)", () => {
    expect(contextText(SOPHIE)).toBe("[profile]\nname: Sophie Martin\njob: Consultante\ndepartment: Engineering\n"
      + "language: French\ntone: concise\n\n[instructions]\nCite toujours l'article.");
    expect(contextText(EMPTY)).toBe("");
  });
});
