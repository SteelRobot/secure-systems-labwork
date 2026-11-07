import { useEffect, useState } from "react";

// Каркас клиента: показывает состояние API. Экраны добавляются вместе с эндпоинтами.
export default function App() {
  const [state, setState] = useState("проверка...");
  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? "API доступен" : `API: ${r.status}`))
      .catch(() => "API недоступен")
      .then(setState);
  }, []);
  return (
    <main style={{ fontFamily: "sans-serif", margin: "2rem" }}>
      <h1>Заявки на материальную поддержку</h1>
      <p>{state}</p>
    </main>
  );
}
