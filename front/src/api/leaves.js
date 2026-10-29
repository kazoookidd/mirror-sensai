import { getJson, putJson } from "./http.js";

// [M1] Every employee's leave requests, and HR's decision on each: HR accounts only
// (the server answers 403 to anyone else).
export const leaves = {
  all: () => getJson("/leave-requests"),
  decide: (id, status) => putJson(`/leave-requests/${id}`, { status }),
};
