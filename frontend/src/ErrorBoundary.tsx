import React from "react";

type BoundaryProps = {
  children: React.ReactNode;
  title?: string;
  compact?: boolean;
  resetKey?: string;
};

type BoundaryState = {
  hasError: boolean;
  message: string;
};

/** 区域或全局 React 错误边界：捕获渲染/Effect 异常，彻底避免整页变死白屏 */
export class ErrorBoundary extends React.Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return {
      hasError: true,
      message: error?.message || "界面渲染遇到异常数据",
    };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // 仅在浏览器本机控制台记录调试信息，不外传任何数据
    console.error("[SignalDesk ErrorBoundary]", error, info?.componentStack);
  }

  componentDidUpdate(prevProps: BoundaryProps) {
    if (
      this.state.hasError &&
      this.props.resetKey !== undefined &&
      prevProps.resetKey !== this.props.resetKey
    ) {
      this.setState({ hasError: false, message: "" });
    }
  }

  handleRecover = () => {
    this.setState({ hasError: false, message: "" });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }
    const { title = "看盘视图暂时遇到异常", compact = false } = this.props;
    return (
      <div
        className={`error-fallback ${compact ? "compact" : "full"}`}
        role="alert"
      >
        <div className="error-fallback-card">
          <h3>{title}</h3>
          <p>
            本机渲染检测到异常状态，已自动拦截以防止页面白屏。您可以点击重试恢复，或刷新当前页面。
          </p>
          {this.state.message && (
            <code className="error-fallback-code">{this.state.message}</code>
          )}
          <div className="error-fallback-actions">
            <button
              type="button"
              className="button primary"
              onClick={this.handleRecover}
            >
              重试渲染
            </button>
            {!compact && (
              <button
                type="button"
                className="button secondary"
                onClick={() => window.location.reload()}
              >
                刷新页面
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }
}
