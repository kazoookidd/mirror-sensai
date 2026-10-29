import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http.js";
import { auth } from "../../api/auth.js";
import { LoginPage } from "./LoginPage.jsx";

const app = { startSession: vi.fn(), ollama: { online: true } };

vi.mock("../../context/AppContext.jsx", () => ({ useApp: () => app }));
vi.mock("../../api/auth.js", () => ({ auth: { login: vi.fn(), signup: vi.fn() } }));
vi.mock("./ThemeToggle.jsx", () => ({ ThemeToggle: () => null }));

const type = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

function openSignup() {
  render(<LoginPage />);
  fireEvent.click(screen.getByRole("button", { name: "Create an employee account" }));
}

function fill({ userId = "camille.m", email = "camille@enterprise.com", password = "longenough", confirm = password } = {}) {
  type("User id", userId);
  type("Email address", email);
  type("Password", password);
  type("Confirm the password", confirm);
  fireEvent.click(screen.getByRole("button", { name: "Create my account" }));
}

describe("LoginPage, signing up [M1]", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("goes from the login form to the sign-up form and back", () => {
    openSignup();
    expect(screen.getByRole("heading", { name: "Create an account" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "I already have an account" }));
    expect(screen.getByRole("heading", { name: "Log in" })).toBeTruthy();
  });

  it("checks the form before sending it", () => {
    openSignup();
    fill({ password: "short" });
    expect(screen.getByRole("alert").textContent).toContain("at least 8 characters");
    fill({ confirm: "different1" });
    expect(screen.getByRole("alert").textContent).toContain("different");
    fill({ userId: "a@b" });
    expect(screen.getByRole("alert").textContent).toContain("user id");
    expect(auth.signup).not.toHaveBeenCalled();
  });

  it("creates the account and opens the session", async () => {
    const account = { user_id: "camille.m", model: "m", account_role: "employee" };
    auth.signup.mockResolvedValue(account);
    openSignup();
    fill({ userId: " camille.m " });
    await vi.waitFor(() => expect(app.startSession).toHaveBeenCalledWith(account));
    expect(auth.signup).toHaveBeenCalledWith("camille.m", "camille@enterprise.com", "longenough", true);
  });

  it("shows why the server refused", async () => {
    auth.signup.mockRejectedValue(new ApiError(409, "This user id is already used."));
    openSignup();
    fill();
    expect((await screen.findByRole("alert")).textContent).toContain("This user id is already used.");
    expect(app.startSession).not.toHaveBeenCalled();
  });
});
