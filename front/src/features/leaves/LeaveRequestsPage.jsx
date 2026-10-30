import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "../../components/feedback/EmptyState/EmptyState.jsx";
import { StatusBadge } from "../../components/ui/Badge/Badge.jsx";
import { InputBox } from "../../components/ui/Field/Field.jsx";
import { Icon } from "../../components/ui/Icon/Icon.jsx";
import { Select } from "../../components/ui/Select/Select.jsx";
import { AppShell } from "../../layout/AppShell.jsx";
import { Page, PageHeader } from "../../layout/Page.jsx";
import { leaves as leavesApi } from "../../api/leaves.js";
import { formatDate, parseUtc } from "../../lib/format.js";
import styles from "./LeaveRequestsPage.module.css";

const ALL = "";

function day(value) {
  const [year, month, date] = value.split("-").map(Number);
  return new Date(year, month - 1, date);
}

export function period(request) {
  const start = formatDate(day(request.start_date));
  return request.start_date === request.end_date ? start : `${start} to ${formatDate(day(request.end_date))}`;
}

function FilterSelect({ label, value, labels, onChange }) {
  const items = [[ALL, `All ${label.toLowerCase()}`], ...Object.entries(labels)].map(([key, text]) => ({
    label: text,
    selected: key === value,
    meta: key === value ? <Icon name="check" size={14} /> : null,
    onSelect: () => onChange(key),
  }));
  return <Select label={label} value={labels[value] ?? `All ${label.toLowerCase()}`} items={items} />;
}

function StatusControl({ request, data, busy, onDecide, block }) {
  const decided = request.decided_by && request.status !== "pending";
  if (!data.decisions.includes(request.status))
    return <span className={styles.cancelled}><StatusBadge status={request.status} /></span>;
  const items = data.decisions.map((status) => ({
    label: data.statuses[status],
    selected: status === request.status,
    meta: status === request.status ? <Icon name="check" size={14} /> : null,
    onSelect: () => status !== request.status && onDecide(request, status),
  }));
  return (
    <span className={styles.status}>
      <span className={styles[`decision_${request.status}`]}>
        {/* floating: the table clips its content (overflow: hidden), the list must be drawn over it */}
        <Select floating block={block} label={`Status of request #${request.id}`} value={busy ? "Saving..." : request.status_label}
          items={items} />
      </span>
      {decided && <span className={styles.decidedBy}>by {request.decided_by}</span>}
    </span>
  );
}

function Employee({ request }) {
  return (
    <span className={styles.employee}>
      <span className="truncate">{request.user_id}</span>
      {request.email && <span className={`${styles.email} truncate`}>{request.email}</span>}
    </span>
  );
}

export function LeaveRequestsPage() {
  const [data, setData] = useState(null);
  const [failure, setFailure] = useState(null);
  const [query, setQuery] = useState("");
  const [type, setType] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [saving, setSaving] = useState(null);
  const [decisionError, setDecisionError] = useState("");

  useEffect(() => {
    leavesApi.all().then(setData).catch((error) => setFailure(error.status === 403 ? "forbidden" : "failed"));
  }, []);

  const decide = async (request, next) => {
    setSaving(request.id);
    setDecisionError("");
    try {
      const { request: saved } = await leavesApi.decide(request.id, next);
      setData((current) => ({ ...current, requests: current.requests.map((item) => (item.id === saved.id ? saved : item)) }));
    } catch (error) {
      setDecisionError(`Request #${request.id}: ${error.message}`);
    }
    setSaving(null);
  };
  const control = (request, block) => (
    <StatusControl request={request} data={data} busy={saving === request.id} onDecide={decide} block={block} />);

  const visible = useMemo(() => {
    const search = query.trim().toLowerCase();
    return (data?.requests ?? []).filter((request) => (
      (!search || `${request.user_id} ${request.email ?? ""} ${request.reason}`.toLowerCase().includes(search))
      && (type === ALL || request.leave_type === type)
      && (status === ALL || request.status === status)));
  }, [data, query, type, status]);

  const requests = data?.requests ?? [];
  return (
    <AppShell nav={{ active: "leaves", mobile: "root", tabs: true }} scroll>
      <Page>
        <PageHeader title="Leave requests" subtitle="Every employee's requests, filed in the chat: approve or refuse them here."
          mobileSubtitle="Approve or refuse the requests." />
        {failure === "forbidden" && (
          <p className="info-note" role="alert"><Icon name="lock" size={16} />Only HR accounts can see the leave requests of every employee.</p>
        )}
        {failure === "failed" && <p className="info-note" role="alert"><Icon name="alert" size={16} />Could not load the leave requests.</p>}
        {data && !requests.length && (
          <div className={styles.emptyCard}>
            <EmptyState icon="users" iconSize={16} title="No leave requests yet">
              Employees file them in the chat; they appear here once confirmed.
            </EmptyState>
          </div>
        )}
        {requests.length > 0 && <>
          <div className={styles.toolbar}>
            <InputBox small leading={["search", 16]} type="search" placeholder="Search an employee or a reason"
              aria-label="Search the leave requests" className={styles.search}
              value={query} onChange={(event) => setQuery(event.target.value)} />
            <FilterSelect label="Types" value={type} labels={data.types} onChange={setType} />
            <FilterSelect label="Statuses" value={status} labels={data.statuses} onChange={setStatus} />
            <span className={styles.count} role="status">{visible.length} of {requests.length}</span>
          </div>
          {decisionError && <p className="info-note" role="alert"><Icon name="alert" size={16} />{decisionError}</p>}
          {!visible.length && <p className="info-note"><Icon name="search" size={16} />No request matches these filters.</p>}
          {visible.length > 0 && <>
            <div className={`${styles.table} desktop-only`} role="table" aria-label="Leave requests">
              <div className={`${styles.row} ${styles.head}`} role="row">
                <span role="columnheader">Employee</span>
                <span role="columnheader">Request</span>
                <span role="columnheader">Filed</span>
                <span role="columnheader">Decision</span>
              </div>
              {visible.map((request) => (
                <div key={request.id} className={styles.row} role="row">
                  <span role="cell"><Employee request={request} /></span>
                  <span role="cell" className={styles.request}>
                    <span className={styles.type}>{request.type_label}</span>
                    <span>{period(request)}</span>
                    {request.reason && <span className={styles.reason}>{request.reason}</span>}
                  </span>
                  <span role="cell" className={styles.cell}>{formatDate(parseUtc(request.created_at))}</span>
                  <span role="cell">{control(request, true)}</span>
                </div>
              ))}
            </div>
            <ul className={`${styles.cards} mobile-only`} aria-label="Leave requests">
              {visible.map((request) => (
                <li key={request.id} className={styles.card}>
                  <div className={styles.cardTop}><Employee request={request} />{control(request)}</div>
                  <p className={styles.cardLine}>{request.type_label} · {period(request)}</p>
                  {request.reason && <p className={styles.cardReason}>{request.reason}</p>}
                </li>
              ))}
            </ul>
          </>}
        </>}
      </Page>
    </AppShell>
  );
}
