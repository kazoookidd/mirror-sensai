import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FormCard } from "./FormCard.jsx";

const QUESTION = {
  title: "Question", plan: "Quel type de congé ?",
  form: { kind: "question", submit_label: "Send", fields: [{ name: "answer", label: "Quel type de congé ?", kind: "choice",
    options: [{ value: "Congés payés", label: "Congés payés" }, { value: "RTT", label: "RTT" }], value: "", required: true, error: "" }] },
};

const LEAVE = {
  title: "Leave request to complete", plan: "Complete your leave request, sophie:",
  form: { kind: "action", submit_label: "File the request", fields: [
    { name: "leave_type", label: "Type", kind: "choice", value: "", required: true, error: "'vacances' is not a type of leave",
      options: [{ value: "paid_leave", label: "Paid leave" }, { value: "bereavement", label: "Bereavement" }] },
    { name: "start_date", label: "First day", kind: "date", options: [], value: "2026-11-03", required: true, error: "" },
    { name: "end_date", label: "Last day", kind: "date", options: [], value: "", required: true, error: "required" },
    { name: "reason", label: "Reason", kind: "text", options: [], value: "deuil", required: false, error: "" },
  ] },
};

describe("FormCard [X4]", () => {
  afterEach(cleanup);

  it("answers a question with one click, or in your own words", () => {
    const onAnswer = vi.fn();
    render(<FormCard {...QUESTION} onAnswer={onAnswer} />);
    fireEvent.click(screen.getByRole("button", { name: "RTT" }));
    expect(onAnswer).toHaveBeenLastCalledWith("RTT");
    fireEvent.change(screen.getByLabelText("Your answer"), { target: { value: " Un congé sans solde " } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onAnswer).toHaveBeenLastCalledWith("Un congé sans solde");
  });

  it("shows the leave form prefilled, with what is missing", () => {
    render(<FormCard {...LEAVE} onSubmit={vi.fn()} />);
    expect(screen.getByLabelText("First day").value).toBe("2026-11-03");
    expect(screen.getByLabelText(/Reason/).value).toBe("deuil");
    expect(screen.getByLabelText("Type").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getAllByRole("alert").map((alert) => alert.textContent)).toEqual(["'vacances' is not a type of leave", "required"]);
  });

  it("submits the values and shows the errors the server returns", async () => {
    const onSubmit = vi.fn().mockResolvedValueOnce({ end_date: "must not be before the first day" });
    render(<FormCard {...LEAVE} onSubmit={onSubmit} />);
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "bereavement" } });
    fireEvent.change(screen.getByLabelText("Last day"), { target: { value: "2026-11-01" } });
    fireEvent.click(screen.getByRole("button", { name: "File the request" }));
    expect(onSubmit).toHaveBeenCalledWith({ leave_type: "bereavement", start_date: "2026-11-03", end_date: "2026-11-01", reason: "deuil" });
    expect((await screen.findByRole("alert")).textContent).toBe("must not be before the first day");
  });

  it("can be cancelled", () => {
    const onCancel = vi.fn();
    render(<FormCard {...LEAVE} onSubmit={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
