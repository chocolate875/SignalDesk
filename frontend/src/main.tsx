import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./ErrorBoundary";
import "./style.css";
const brokerResult = new URLSearchParams(location.search).get("broker-result");
const resultMessages: Record<string, string> = {
  success: "长桥授权已保存",
  cancelled: "本次授权未完成",
  invalid: "授权链接已失效或与当前浏览器不匹配",
  failed: "长桥授权未保存",
};
if (brokerResult) {
  document.documentElement.dataset.theme =
    localStorage.getItem("sd-theme-v2") ?? "light";
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {brokerResult && Object.hasOwn(resultMessages, brokerResult) ? (
      <main className="broker-result">
        <h1>{resultMessages[brokerResult]}</h1>
        <p>
          {brokerResult === "success"
            ? "可关闭此页，回到 SignalDesk 选择实盘模式。"
            : "请回到 SignalDesk 的「长桥数据」重新发起授权。"}
        </p>
        <a className="button secondary" href="/">
          打开看板
        </a>
      </main>
    ) : (
      <ErrorBoundary title="SignalDesk 看板遇到渲染异常">
        <App />
      </ErrorBoundary>
    )}
  </React.StrictMode>,
);
