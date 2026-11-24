import { useEffect, useState } from "react";

interface User {
  id: string;
  full_name: string;
  email: string;
  role: string;
  department_id: string | null;
}

interface ApplicationListItem {
  id: string;
  applicant_id: string;
  support_type: string;
  academic_year: number;
  status: string;
  requested_amount: number | null;
  created_at: string;
}

interface DocumentItem {
  id: string;
  original_name: string;
  file_size: number;
  mime_type: string;
  uploaded_at: string;
  download_url: string;
}

interface ApplicationDetail extends ApplicationListItem {
  approved_amount: number | null;
  comment: string | null;
  decision_comment: string | null;
  submitted_at: string | null;
  updated_at: string;
  documents: DocumentItem[];
}

const SUPPORT_NAMES: Record<string, string> = {
  material_support: "Материальная помощь",
  state_academic_scholarship: "Государственная академическая стипендия",
  pgas: "Повышенная государственная академическая стипендия (ПГАС)",
};

const STATUS_NAMES: Record<string, { label: string; color: string; bg: string }> = {
  draft: { label: "Черновик", color: "#495057", bg: "#e9ecef" },
  submitted: { label: "Отправлена", color: "#1971c2", bg: "#e7f5ff" },
  under_review: { label: "На рассмотрении", color: "#f59f00", bg: "#fff9db" },
  needs_revision: { label: "На доработке", color: "#d9480f", bg: "#ffe8cc" },
  approved: { label: "Одобрена", color: "#2b8a3e", bg: "#ebfbee" },
  rejected: { label: "Отклонена", color: "#c92a2a", bg: "#ffe3e3" },
  cancelled: { label: "Отозвана", color: "#868e96", bg: "#f1f3f5" },
};

const ROLE_NAMES: Record<string, string> = {
  applicant: "Заявитель",
  employee: "Ответственный сотрудник",
  technical_admin: "Технический специалист",
};

export default function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  // Application form states
  const [supportType, setSupportType] = useState("material_support");
  const [academicYear, setAcademicYear] = useState(2026);
  const [requestedAmount, setRequestedAmount] = useState("");
  const [comment, setComment] = useState("");
  const [createdApp, setCreatedApp] = useState<ApplicationDetail | null>(null);
  const [viewAppId, setViewAppId] = useState("");
  const [fetchedApp, setFetchedApp] = useState<ApplicationDetail | null>(null);
  const [fetchedAppCheckList, setFetchedAppCheckList] = useState<any[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Application List
  const [appList, setAppList] = useState<ApplicationListItem[]>([]);

  useEffect(() => {
    const savedToken = sessionStorage.getItem("access_token");
    const savedUser = sessionStorage.getItem("user");
    if (savedToken && savedUser) {
      setToken(savedToken);
      setUser(JSON.parse(savedUser));
    }
  }, []);

  const loadApplications = async (authToken: string) => {
    try {
      const res = await fetch("/api/applications", {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        setAppList(data.items || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (token) {
      loadApplications(token);
    }
  }, [token]);

  
  const handleDownloadDoc = async (docUrl: string) => {
    try {
      const res = await fetch(docUrl, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Ошибка открытия файла");
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      window.open(url, "_blank");
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Ошибка авторизации");

      sessionStorage.setItem("access_token", data.access_token);
      sessionStorage.setItem("user", JSON.stringify(data.user));
      setToken(data.access_token);
      setUser(data.user);
      setPassword("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateApp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setCreatedApp(null);

    try {
      const res = await fetch("/api/applications", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "Idempotency-Key": `ui-${Date.now()}`
        },
        body: JSON.stringify({
          support_type: supportType,
          academic_year: Number(academicYear),
          requested_amount: requestedAmount ? Number(requestedAmount) : null,
          comment,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Ошибка создания заявки");

      setCreatedApp(data);
      setComment("");
      setRequestedAmount("");
      if (token) loadApplications(token);
      fetchDetail(data.id);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const fetchDetail = async (id: string) => {
    setFetchError(null);
    setFetchedApp(null);
    setFetchedAppCheckList([]);
    setViewAppId(id);

    try {
      const res = await fetch(`/api/applications/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Ошибка получения заявки");
      setFetchedApp(data);

      // Загрузка списка проверок для заявки
      try {
        const checkRes = await fetch(`/api/applications/${id}/completeness-check`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (checkRes.ok) {
          const checkData = await checkRes.json();
          setFetchedAppCheckList(checkData);
        }
      } catch (e) {
        setFetchedAppCheckList([]);
      }
    } catch (err: any) {
      setFetchError(err.message);
    }
  };

  const handleFetchByInput = async (e: React.FormEvent) => {
    e.preventDefault();
    if (viewAppId.trim()) {
      fetchDetail(viewAppId.trim());
    }
  };

  const handleLogout = async () => {
    if (token) {
      try {
        await fetch("/api/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` }
        });
      } catch (e) {}
    }
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("user");
    setToken(null);
    setUser(null);
    setCreatedApp(null);
    setFetchedApp(null);
    setAppList([]);
  };

  return (
    <main style={{ fontFamily: "system-ui, -apple-system, sans-serif", maxWidth: "720px", margin: "2rem auto", padding: "1rem" }}>
      <header style={{ borderBottom: "2px solid #eaeaea", paddingBottom: "1rem", marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", margin: 0, color: "#111" }}>
          Система заявок на материальную поддержку
        </h1>
        <p style={{ margin: "0.5rem 0 0 0", color: "#666", fontSize: "0.9rem" }}>
          Университетский сервис приёма и обработки обращений
        </p>
      </header>

      {user ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* User info card */}
          <section style={{ background: "#f8f9fa", border: "1px solid #e9ecef", borderRadius: "8px", padding: "1.5rem" }}>
            <h2 style={{ margin: "0 0 1rem 0", fontSize: "1.2rem", color: "#2b8a3e" }}>
              ✓ Успешный вход в систему
            </h2>
            <table style={{ width: "100%", textAlign: "left", fontSize: "0.95rem", borderCollapse: "collapse" }}>
              <tbody>
                <tr>
                  <td style={{ padding: "4px 0", color: "#666", width: "140px" }}>ФИО:</td>
                  <td style={{ padding: "4px 0", fontWeight: "bold" }}>{user.full_name}</td>
                </tr>
                <tr>
                  <td style={{ padding: "4px 0", color: "#666" }}>Email:</td>
                  <td style={{ padding: "4px 0" }}>{user.email}</td>
                </tr>
                <tr>
                  <td style={{ padding: "4px 0", color: "#666" }}>Роль:</td>
                  <td style={{ padding: "4px 0" }}>
                    <span style={{ background: "#e7f5ff", color: "#1971c2", padding: "2px 8px", borderRadius: "4px", fontSize: "0.85rem", fontWeight: 600 }}>
                      {ROLE_NAMES[user.role] || user.role}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: "4px 0", color: "#666" }}>Токен (JWT):</td>
                  <td style={{ padding: "4px 0", fontFamily: "monospace", fontSize: "0.8rem", wordBreak: "break-all", color: "#495057" }}>
                    {token?.slice(0, 30)}...
                  </td>
                </tr>
              </tbody>
            </table>

            <button
              onClick={handleLogout}
              style={{
                marginTop: "1.5rem",
                padding: "0.6rem 1.2rem",
                background: "#fa5252",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
                fontWeight: 600
              }}
            >
              Выйти из системы
            </button>
          </section>

          {/* Create Application Form (for applicants) */}
          {user.role === "applicant" && (
            <section style={{ background: "#fff", border: "1px solid #dee2e6", borderRadius: "8px", padding: "1.2rem" }}>
              <h2 style={{ margin: "0 0 1rem 0", fontSize: "1.1rem" }}>1. Создать новую заявку (POST /api/applications)</h2>
              {error && <div style={{ background: "#ffe3e3", color: "#c92a2a", padding: "0.6rem", borderRadius: "4px", marginBottom: "1rem", fontSize: "0.85rem" }}>{error}</div>}

              <form onSubmit={handleCreateApp} style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.2rem" }}>Тип поддержки:</label>
                  <select value={supportType} onChange={e => setSupportType(e.target.value)} style={{ width: "100%", padding: "0.4rem" }}>
                    <option value="material_support">Материальная помощь</option>
                    <option value="state_academic_scholarship">Государственная академическая стипендия</option>
                    <option value="pgas">ПГАС</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.2rem" }}>Учебный год:</label>
                  <input type="number" value={academicYear} onChange={e => setAcademicYear(Number(e.target.value))} style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }} />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.2rem" }}>Запрашиваемая сумма (руб):</label>
                  <input type="number" value={requestedAmount} onChange={e => setRequestedAmount(e.target.value)} placeholder="например 10000" style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }} />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.2rem" }}>Обоснование обращения (комментарий):</label>
                  <textarea required rows={3} value={comment} onChange={e => setComment(e.target.value)} placeholder="Опишите причину обращения..." style={{ width: "100%", padding: "0.4rem", boxSizing: "border-box" }} />
                </div>
                <button type="submit" style={{ padding: "0.6rem", background: "#2b8a3e", color: "#fff", border: "none", borderRadius: "4px", fontWeight: 600, cursor: "pointer" }}>
                  Создать заявку (черновик)
                </button>
              </form>

              {createdApp && (
                <div style={{ marginTop: "1rem", padding: "0.8rem", background: "#ebfbee", border: "1px solid #b2f2bb", borderRadius: "4px", fontSize: "0.85rem" }}>
                  <div style={{ fontWeight: 600, color: "#2b8a3e" }}>✓ Заявка успешно создана!</div>
                  <div>ID заявки: <code>{createdApp.id}</code></div>
                  <div>Статус: <b>{createdApp.status}</b></div>
                </div>
              )}
            </section>
          )}

          {/* Applications list table */}
          <section style={{ background: "#fff", border: "1px solid #dee2e6", borderRadius: "8px", padding: "1.2rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h2 style={{ margin: 0, fontSize: "1.1rem" }}>
                2. Список доступных заявок (GET /api/applications)
              </h2>
              {user.role === "employee" && (
                <button
                  onClick={async () => {
                    try {
                      const res = await fetch("/api/reports/applications", {
                        method: "GET",
                        headers: { Authorization: `Bearer ${token}` }
                      });
                      const data = await res.json();
                      if (!res.ok) throw new Error(data.detail || "Ошибка запроса отчёта");
                      alert("Запрос на формирование отчёта отправлен. Ожидание завершения...");
                      
                      setTimeout(async () => {
                        const stRes = await fetch(`/api/reports/${data.report_id}`, {
                          headers: { Authorization: `Bearer ${token}` }
                        });
                        const stData = await stRes.json();
                        if (stData.status === "completed" && stData.download_url) {
                          handleDownloadDoc(stData.download_url);
                        } else {
                          alert("Отчёт формируется, попробуйте позже.");
                        }
                      }, 2000);
                    } catch (err: any) { alert(err.message); }
                  }}
                  style={{ padding: "0.4rem 0.8rem", background: "#1971c2", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: 600, fontSize: "0.85rem" }}
                >
                  Сформировать и скачать сводный отчёт (CSV)
                </button>
              )}
            </div>
            {appList.length === 0 ? (
              <div style={{ color: "#666", fontSize: "0.9rem" }}>Заявок пока нет</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.85rem" }}>
                <thead>
                  <tr style={{ background: "#f8f9fa", borderBottom: "2px solid #dee2e6" }}>
                    <th style={{ padding: "8px" }}>Тип</th>
                    <th style={{ padding: "8px" }}>Год</th>
                    <th style={{ padding: "8px" }}>Статус</th>
                    <th style={{ padding: "8px" }}>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {appList.map(item => (
                    <tr key={item.id} style={{ borderBottom: "1px solid #f1f3f5" }}>
                      <td style={{ padding: "8px" }}>{SUPPORT_NAMES[item.support_type] || item.support_type}</td>
                      <td style={{ padding: "8px" }}>{item.academic_year}</td>
                      <td style={{ padding: "8px" }}>
                        <span style={{ background: STATUS_NAMES[item.status]?.bg, color: STATUS_NAMES[item.status]?.color, padding: "2px 6px", borderRadius: "4px", fontWeight: 600 }}>
                          {STATUS_NAMES[item.status]?.label || item.status}
                        </span>
                      </td>
                      <td style={{ padding: "8px" }}>
                        <button
                          onClick={() => fetchDetail(item.id)}
                          style={{ padding: "0.2rem 0.6rem", fontSize: "0.8rem", background: "#e7f5ff", color: "#1971c2", border: "1px solid #a5d8ff", borderRadius: "4px", cursor: "pointer", fontWeight: 600 }}
                        >
                          Открыть
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* Selected Application Details */}
          {(fetchedApp || fetchError) && (
            <section style={{ background: "#fff", border: "1px solid #dee2e6", borderRadius: "8px", padding: "1.2rem" }}>
              <h2 style={{ margin: "0 0 1rem 0", fontSize: "1.1rem" }}>3. Детали заявки</h2>

              {fetchError && (
                <div style={{ background: "#ffe3e3", color: "#c92a2a", padding: "0.6rem", borderRadius: "4px", fontSize: "0.85rem" }}>
                  {fetchError}
                </div>
              )}

              {fetchedApp && (
                <div style={{ background: "#f8f9fa", border: "1px solid #e9ecef", borderRadius: "4px", padding: "0.8rem", fontSize: "0.85rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                    <span style={{ fontWeight: 600 }}>{SUPPORT_NAMES[fetchedApp.support_type] || fetchedApp.support_type}</span>
                    <span style={{ background: STATUS_NAMES[fetchedApp.status]?.bg || "#eee", color: STATUS_NAMES[fetchedApp.status]?.color || "#333", padding: "2px 6px", borderRadius: "4px", fontWeight: 600 }}>
                      {STATUS_NAMES[fetchedApp.status]?.label || fetchedApp.status}
                    </span>
                  </div>
                  <div><b>ID:</b> <code>{fetchedApp.id}</code></div>
                  <div><b>Заявитель ID:</b> <code>{fetchedApp.applicant_id}</code></div>
                  <div><b>Год:</b> {fetchedApp.academic_year}</div>
                  {fetchedApp.requested_amount && <div><b>Сумма:</b> {fetchedApp.requested_amount} руб.</div>}
                  <div><b>Обоснование:</b> {fetchedApp.comment}</div>
                  {fetchedApp.approved_amount && <div><b>Одобренная сумма:</b> {fetchedApp.approved_amount} руб.</div>}
                  {fetchedApp.decision_comment && (
                    <div style={{ marginTop: "0.4rem", padding: "0.5rem 0.8rem", background: "#fff9db", borderLeft: "3px solid #f59f00", borderRadius: "4px" }}>
                      <b>Комментарий сотрудника:</b> {fetchedApp.decision_comment}
                    </div>
                  )}
                  {/* Форма принятия решения для ответственного сотрудника */}
                  {user.role === "employee" && fetchedApp.status !== "draft" && (
                    <div style={{ marginTop: "1rem", paddingTop: "0.8rem", borderTop: "1px solid #dee2e6" }}>
                      <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Управление состоянием заявки:</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                        {fetchedApp.status === "submitted" && (
                          <button
                            onClick={async () => {
                              const comment = prompt("Комментарий (необязательно):") || "";
                              try {
                                const res = await fetch(`/api/applications/${fetchedApp.id}/status`, {
                                  method: "PATCH",
                                  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                                  body: JSON.stringify({ status: "under_review", decision_comment: comment }),
                                });
                                if (!res.ok) throw new Error((await res.json()).detail);
                                fetchDetail(fetchedApp.id);
                                if (token) loadApplications(token);
                              } catch (err: any) { alert(err.message); }
                            }}
                            style={{ padding: "0.4rem 0.8rem", background: "#f59f00", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}
                          >
                            Взять на рассмотрение
                          </button>
                        )}

                        {fetchedApp.status === "under_review" && (
                          <>
                            <button
                              onClick={async () => {
                                const comment = prompt("Причина возврата на доработку:");
                                if (!comment) return;
                                try {
                                  const res = await fetch(`/api/applications/${fetchedApp.id}/status`, {
                                    method: "PATCH",
                                    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                                    body: JSON.stringify({ status: "needs_revision", decision_comment: comment }),
                                  });
                                  if (!res.ok) throw new Error((await res.json()).detail);
                                  fetchDetail(fetchedApp.id);
                                  if (token) loadApplications(token);
                                } catch (err: any) { alert(err.message); }
                              }}
                              style={{ padding: "0.4rem 0.8rem", background: "#d9480f", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}
                            >
                              Вернуть на доработку
                            </button>

                            <button
                              onClick={async () => {
                                const amountStr = prompt("Одобренная сумма (руб):", fetchedApp.requested_amount?.toString() || "");
                                const comment = prompt("Комментарий к решению:") || "Одобрено";
                                const amount = amountStr ? Number(amountStr) : null;
                                try {
                                  const res = await fetch(`/api/applications/${fetchedApp.id}/status`, {
                                    method: "PATCH",
                                    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                                    body: JSON.stringify({ status: "approved", approved_amount: amount, decision_comment: comment }),
                                  });
                                  if (!res.ok) throw new Error((await res.json()).detail);
                                  fetchDetail(fetchedApp.id);
                                  if (token) loadApplications(token);
                                } catch (err: any) { alert(err.message); }
                              }}
                              style={{ padding: "0.4rem 0.8rem", background: "#2b8a3e", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}
                            >
                              Одобрить заявку
                            </button>

                            <button
                              onClick={async () => {
                                const comment = prompt("Причина отказа:");
                                if (!comment) return;
                                try {
                                  const res = await fetch(`/api/applications/${fetchedApp.id}/status`, {
                                    method: "PATCH",
                                    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                                    body: JSON.stringify({ status: "rejected", decision_comment: comment }),
                                  });
                                  if (!res.ok) throw new Error((await res.json()).detail);
                                  fetchDetail(fetchedApp.id);
                                  if (token) loadApplications(token);
                                } catch (err: any) { alert(err.message); }
                              }}
                              style={{ padding: "0.4rem 0.8rem", background: "#c92a2a", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}
                            >
                              Отклонить заявку
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Прикрепленные документы */}
                  <div style={{ marginTop: "0.8rem", paddingTop: "0.8rem", borderTop: "1px solid #dee2e6" }}>
                    <div style={{ fontWeight: 600, marginBottom: "0.4rem" }}>Прикреплённые документы:</div>
                    {(!fetchedApp.documents || (fetchedApp.documents as any[]).length === 0) ? (
                      <div style={{ color: "#868e96" }}>Документы пока не прикреплены</div>
                    ) : (
                      <ul style={{ margin: "0.3rem 0", paddingLeft: "1.2rem" }}>
                        {(fetchedApp.documents as any[]).map((d: any) => (
                          <li key={d.id} style={{ marginBottom: "0.2rem" }}>
                            <button
                              type="button"
                              onClick={() => handleDownloadDoc(d.download_url)}
                              style={{
                                background: "none",
                                border: "none",
                                padding: 0,
                                color: "#1971c2",
                                fontWeight: 600,
                                textDecoration: "underline",
                                cursor: "pointer",
                                fontSize: "0.85rem"
                              }}
                            >
                              📄 {d.original_name}
                            </button>{" "}
                            <span style={{ color: "#868e96", fontSize: "0.75rem" }}>
                              ({(d.file_size / 1024).toFixed(1)} КБ)
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {/* Форма загрузки документа для заявителя в статусе draft */}
		  {fetchedApp.status !== "submitted" && fetchedApp.status !== "approved" && fetchedApp.status !== "rejected" && fetchedApp.status !== "cancelled" && (user.role === "applicant" || user.role === "employee") && (
                    <form
                      onSubmit={async (e) => {
                        e.preventDefault();
                        const form = e.target as HTMLFormElement;
                        const fileInput = form.elements.namedItem("docFile") as HTMLInputElement;
                        if (!fileInput || !fileInput.files || fileInput.files.length === 0) return;

                        const formData = new FormData();
                        formData.append("file", fileInput.files[0]);

                        try {
                          const res = await fetch(`/api/applications/${fetchedApp.id}/documents`, {
                            method: "POST",
                            headers: { Authorization: `Bearer ${token}` },
                            body: formData,
                          });
                          const data = await res.json();
                          if (!res.ok) throw new Error(data.detail || "Ошибка загрузки документа");
                          fileInput.value = "";
                          fetchDetail(fetchedApp.id);
                        } catch (err: any) {
                          alert(err.message);
                        }
                      }}
                      style={{ marginTop: "0.8rem", paddingTop: "0.8rem", borderTop: "1px dashed #ced4da", display: "flex", gap: "0.5rem", alignItems: "center" }}
                    >
		    {fetchedApp.status !== "submitted" && fetchedApp.status !== "approved" && fetchedApp.status !== "rejected" && fetchedApp.status !== "cancelled" && (user.role === "applicant" || user.role === "employee") && (
                      <input type="file" name="docFile" accept=".pdf,.png,.jpg,.jpeg" required style={{ fontSize: "0.8rem" }} /> )}
                  {fetchedApp.status !== "submitted" && fetchedApp.status !== "approved" && fetchedApp.status !== "rejected" && fetchedApp.status !== "cancelled" && (user.role === "applicant" || user.role === "employee") && (
                      <button type="submit" style={{ padding: "0.3rem 0.8rem", fontSize: "0.8rem", background: "#2b8a3e", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: 600 }}>
                        Прикрепить документ
                      </button>
		      )}
                    </form>
                  )}

                                    {/* Кнопка отправки заявки из draft в submitted */}
                  {fetchedApp.status !== "submitted" && fetchedApp.status !== "approved" && fetchedApp.status !== "rejected" && fetchedApp.status !== "cancelled" && (user.role === "applicant" || user.role === "employee") && (
                    <div style={{ marginTop: "1rem", paddingTop: "0.8rem", borderTop: "1px solid #dee2e6" }}>
                      <button
                        onClick={async () => {
                          if (!confirm("Вы уверены, что хотите отправить заявку? После отправки её нельзя будет редактировать.")) return;
                          try {
                            const res = await fetch(`/api/applications/${fetchedApp.id}/submit`, {
                              method: "PATCH",
                              headers: {
                                Authorization: `Bearer ${token}`,
                                "Idempotency-Key": `submit-ui-${Date.now()}`
                              },
                            });
                            const data = await res.json();
                            if (!res.ok) throw new Error(data.detail || "Ошибка отправки заявки");
                            fetchDetail(fetchedApp.id);
                            if (token) loadApplications(token);
                          } catch (err: any) {
                            alert(err.message);
                          }
                        }}
                        style={{ padding: "0.6rem 1.2rem", background: "#1971c2", color: "#fff", border: "none", borderRadius: "4px", fontWeight: 600, cursor: "pointer" }}
                      >
                        Отправить заявку в подразделение
                      </button>
                    </div>
                  )}
                  
                  {/* Секция ИИ-проверки полноты заявки */}
                  <div style={{ marginTop: "1rem", paddingTop: "0.8rem", borderTop: "1px solid #dee2e6" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                      <span style={{ fontWeight: 600 }}>Проверка полноты обращения:</span>
                      {fetchedApp.status !== "submitted" && fetchedApp.status !== "approved" && fetchedApp.status !== "rejected" && fetchedApp.status !== "cancelled" && (user.role === "applicant" || user.role === "employee") && (
                        <button
                          onClick={async () => {
                            try {
                              const res = await fetch(`/api/applications/${fetchedApp.id}/completeness-check`, {
                                method: "POST",
                                headers: { Authorization: `Bearer ${token}` }
                              });
                              const data = await res.json();
                              if (!res.ok) throw new Error(data.detail || "Ошибка запуска проверки");
                              alert("Проверка запущена! Результат обновится через секунду.");
                              setTimeout(() => fetchDetail(fetchedApp.id), 1500);
                            } catch (err: any) { alert(err.message); }
                          }}
                          style={{ padding: "0.3rem 0.6rem", fontSize: "0.8rem", background: "#e7f5ff", color: "#1971c2", border: "1px solid #a5d8ff", borderRadius: "4px", cursor: "pointer" }}
                        >
                          Запустить проверку
                        </button>
                      )}
                    </div>

                    {fetchedAppCheckList && fetchedAppCheckList.length > 0 ? (
                      <div style={{ background: "#fff", border: "1px solid #e9ecef", borderRadius: "4px", padding: "0.6rem", fontSize: "0.8rem" }}>
                        <div style={{ marginBottom: "0.3rem" }}>
                          <b>Статус:</b> {fetchedAppCheckList[0].status === "completed" ? "Завершена" : "Обрабатывается..."}
                        </div>
                        {fetchedAppCheckList[0].issues && fetchedAppCheckList[0].issues.length > 0 && (
                          <div style={{ marginBottom: "0.3rem" }}>
                            <b>Замечания:</b>
                            <ul style={{ margin: "0.2rem 0", paddingLeft: "1rem" }}>
                              {fetchedAppCheckList[0].issues.map((issue: string, idx: number) => (
                                <li key={idx}>{issue}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {fetchedAppCheckList[0].recommendations && fetchedAppCheckList[0].recommendations.length > 0 && (
                          <div>
                            <b>Выводы:</b>
                            <ul style={{ margin: "0.2rem 0", paddingLeft: "1rem" }}>
                              {fetchedAppCheckList[0].recommendations.map((rec: string, idx: number) => (
                                <li key={idx}>{rec}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div style={{ color: "#868e96", fontSize: "0.8rem" }}>Проверка ещё не проводилась</div>
                    )}
                  </div>
                  <div style={{ color: "#868e96", marginTop: "0.8rem", fontSize: "0.75rem" }}>Создана: {new Date(fetchedApp.created_at).toLocaleString()}</div>
                </div>
              )}
            </section>
          )}

          {/* Direct UUID lookup field for manual testing */}
          <section style={{ background: "#fff", border: "1px solid #dee2e6", borderRadius: "8px", padding: "1.2rem" }}>
            <h2 style={{ margin: "0 0 0.5rem 0", fontSize: "0.95rem", color: "#666" }}>Проверка доступа по произвольному UUID:</h2>
            <form onSubmit={handleFetchByInput} style={{ display: "flex", gap: "0.5rem" }}>
              <input
                type="text"
                required
                placeholder="Вставьте чужой UUID для проверки"
                value={viewAppId}
                onChange={e => setViewAppId(e.target.value)}
                style={{ flex: 1, padding: "0.4rem", boxSizing: "border-box", fontSize: "0.85rem" }}
              />
              <button type="submit" style={{ padding: "0.4rem 0.8rem", background: "#495057", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "0.85rem" }}>
                Запросить
              </button>
            </form>
          </section>
        </div>
      ) : (
        <section style={{ background: "#fff", border: "1px solid #dee2e6", borderRadius: "8px", padding: "1.5rem", boxShadow: "0 2px 4px rgba(0,0,0,0.05)" }}>
          <h2 style={{ margin: "0 0 1rem 0", fontSize: "1.2rem" }}>Вход в систему</h2>

          {error && (
            <div style={{ background: "#ffe3e3", color: "#c92a2a", padding: "0.75rem", borderRadius: "4px", marginBottom: "1rem", fontSize: "0.9rem" }}>
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div>
              <label style={{ display: "block", marginBottom: "0.3rem", fontSize: "0.9rem", color: "#495057" }}>
                Электронная почта
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@univ.local"
                style={{ width: "100%", padding: "0.5rem", border: "1px solid #ced4da", borderRadius: "4px", boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", marginBottom: "0.3rem", fontSize: "0.9rem", color: "#495057" }}>
                Пароль
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ width: "100%", padding: "0.5rem", border: "1px solid #ced4da", borderRadius: "4px", boxSizing: "border-box" }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                padding: "0.7rem",
                background: "#228be6",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                fontWeight: 600,
                cursor: loading ? "not-allowed" : "pointer"
              }}
            >
              {loading ? "Выполняется вход..." : "Войти"}
            </button>
          </form>

          {/* Быстрые формы: Регистрация / Восстановление доступа */}
          <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid #dee2e6", fontSize: "0.85rem" }}>
            <details>
              <summary style={{ cursor: "pointer", color: "#1971c2", fontWeight: 600 }}>Регистрация нового заявителя</summary>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const form = e.target as HTMLFormElement;
                  const uid = (form.elements.namedItem("regUid") as HTMLInputElement).value;
                  const name = (form.elements.namedItem("regName") as HTMLInputElement).value;
                  const regEmail = (form.elements.namedItem("regEmail") as HTMLInputElement).value;
                  const regPass = (form.elements.namedItem("regPass") as HTMLInputElement).value;

                  try {
                    const res = await fetch("/api/auth/register", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ university_id: uid, full_name: name, email: regEmail, password: regPass }),
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || "Ошибка регистрации");
                    alert("Регистрация успешна! Теперь вы можете войти.");
                    setEmail(regEmail);
                    setPassword(regPass);
                  } catch (err: any) { alert(err.message); }
                }}
                style={{ marginTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}
              >
                <input name="regUid" placeholder="Номер студенческого/удостоверения (S-9999)" required style={{ padding: "0.3rem" }} />
                <input name="regName" placeholder="ФИО заявителя" required style={{ padding: "0.3rem" }} />
                <input name="regEmail" type="email" placeholder="Email (new_user@univ.local)" required style={{ padding: "0.3rem" }} />
                <input name="regPass" type="password" placeholder="Пароль (мин. 8 символов)" required style={{ padding: "0.3rem" }} />
                <button type="submit" style={{ padding: "0.4rem", background: "#2b8a3e", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>
                  Зарегистрироваться
                </button>
              </form>
            </details>

            <details style={{ marginTop: "0.5rem" }}>
              <summary style={{ cursor: "pointer", color: "#1971c2", fontWeight: 600 }}>Забыли пароль? (Восстановление)</summary>
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const form = e.target as HTMLFormElement;
                  const resetEmail = (form.elements.namedItem("resetEmail") as HTMLInputElement).value;

                  try {
                    const res = await fetch("/api/auth/password-reset", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ email: resetEmail }),
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || "Ошибка запроса");
                    alert("Код отправлен в локальный почтовый сервис Mailpit (https://localhost:8025)!");
                  } catch (err: any) { alert(err.message); }
                }}
                style={{ marginTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}
              >
                <input name="resetEmail" type="email" placeholder="Введите ваш Email" required style={{ padding: "0.3rem" }} />
                <button type="submit" style={{ padding: "0.4rem", background: "#f59f00", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>
                  Запросить код в Mailpit
                </button>
              </form>

              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const form = e.target as HTMLFormElement;
                  const resetEmail = (form.elements.namedItem("confirmEmail") as HTMLInputElement).value;
                  const code = (form.elements.namedItem("confirmCode") as HTMLInputElement).value;
                  const newPass = (form.elements.namedItem("confirmPass") as HTMLInputElement).value;

                  try {
                    const res = await fetch("/api/auth/password-reset/confirm", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ email: resetEmail, reset_code: code, new_password: newPass }),
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || "Ошибка смены пароля");
                    alert("Пароль успешно изменён! Войдите с новым паролем.");
                    setEmail(resetEmail);
                    setPassword(newPass);
                  } catch (err: any) { alert(err.message); }
                }}
                style={{ marginTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem", borderTop: "1px dashed #ccc", paddingTop: "0.5rem" }}
              >
                <input name="confirmEmail" type="email" placeholder="Email" required style={{ padding: "0.3rem" }} />
                <input name="confirmCode" placeholder="6-значный код из Mailpit" required style={{ padding: "0.3rem" }} />
                <input name="confirmPass" type="password" placeholder="Новый пароль" required style={{ padding: "0.3rem" }} />
                <button type="submit" style={{ padding: "0.4rem", background: "#1971c2", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}>
                  Подтвердить смену пароля
                </button>
              </form>
            </details>
          </div>

        </section>
      )}
    </main>
  );
}
