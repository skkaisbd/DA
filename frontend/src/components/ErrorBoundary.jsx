import React from 'react';
import { AlertTriangle, Home, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GlassCard } from '@/components/ui/glass';

/**
 * ErrorBoundary Component
 * Catches JavaScript errors anywhere in the component tree and displays a fallback UI
 * 
 * Usage:
 * <ErrorBoundary level="root" fallback={<CustomFallback />}>
 *   <YourComponent />
 * </ErrorBoundary>
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorCount: 0,
    };
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render will show the fallback UI
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    // Log error details
    const errorDetails = {
      error: error.toString(),
      errorInfo: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
      level: this.props.level || 'unknown',
      userAgent: navigator.userAgent,
    };

    // Log to console
    console.error('🔴 ErrorBoundary caught an error:', errorDetails);

    // Store in sessionStorage for debugging (keep last 10 errors)
    try {
      const stored = JSON.parse(sessionStorage.getItem('app_errors') || '[]');
      stored.push(errorDetails);
      if (stored.length > 10) stored.shift();
      sessionStorage.setItem('app_errors', JSON.stringify(stored));
    } catch (e) {
      console.error('Failed to store error in sessionStorage:', e);
    }

    // Update state with error details
    this.setState({
      error,
      errorInfo,
      errorCount: this.state.errorCount + 1,
    });

    // Call optional onError callback
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
    
    // Call optional onReset callback
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return typeof this.props.fallback === 'function'
          ? this.props.fallback(this.state.error, this.handleReset)
          : this.props.fallback;
      }

      // Default fallback UI based on level
      const level = this.props.level || 'module';
      
      return <ErrorFallback 
        level={level}
        error={this.state.error}
        errorInfo={this.state.errorInfo}
        errorCount={this.state.errorCount}
        onReset={this.handleReset}
        onReload={this.handleReload}
        onGoHome={this.handleGoHome}
      />;
    }

    return this.props.children;
  }
}

/**
 * Default Error Fallback UI
 */
function ErrorFallback({ level, error, errorInfo, errorCount, onReset, onReload, onGoHome }) {
  const isDev = process.env.NODE_ENV === 'development';
  
  // Different UI based on error boundary level
  if (level === 'root') {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-background">
        <div className="max-w-2xl w-full space-y-6">
          <div className="text-center">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-red-500/10 mb-6">
              <AlertTriangle className="w-10 h-10 text-red-500" />
            </div>
            <h1 className="text-3xl font-bold text-foreground mb-2">Oops! Terjadi Kesalahan</h1>
            <p className="text-muted-foreground text-lg">
              Aplikasi mengalami error yang tidak terduga. Kami mohon maaf atas ketidaknyamanan ini.
            </p>
          </div>

          <GlassCard className="p-6 space-y-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold text-foreground mb-1">Detail Error</h3>
                <p className="text-xs text-muted-foreground break-words">
                  {error?.toString() || 'Unknown error'}
                </p>
                {errorCount > 1 && (
                  <p className="text-xs text-amber-600 mt-2">
                    ⚠️ Error ini terjadi {errorCount} kali berturut-turut
                  </p>
                )}
              </div>
            </div>

            {isDev && errorInfo && (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground font-medium mb-2">
                  Stack Trace (Dev Only)
                </summary>
                <pre className="bg-muted/50 p-3 rounded overflow-auto max-h-64 text-xs">
                  {errorInfo.componentStack}
                </pre>
              </details>
            )}
          </GlassCard>

          <div className="flex flex-col sm:flex-row gap-3">
            <Button onClick={onReload} className="flex-1" size="lg">
              <RefreshCw className="w-4 h-4 mr-2" />
              Muat Ulang Halaman
            </Button>
            <Button onClick={onGoHome} variant="outline" className="flex-1" size="lg">
              <Home className="w-4 h-4 mr-2" />
              Ke Halaman Utama
            </Button>
          </div>

          <p className="text-xs text-center text-muted-foreground">
            Jika error terus terjadi, silakan hubungi administrator sistem.
          </p>
        </div>
      </div>
    );
  }

  if (level === 'portal') {
    return (
      <div className="flex items-center justify-center min-h-[60vh] p-6">
        <GlassCard className="max-w-lg w-full p-6 space-y-4">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center shrink-0">
              <AlertTriangle className="w-6 h-6 text-red-500" />
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-xl font-bold text-foreground mb-1">Portal Error</h2>
              <p className="text-sm text-muted-foreground mb-3">
                Portal ini mengalami error. Silakan coba lagi atau kembali ke dashboard.
              </p>
              <p className="text-xs text-muted-foreground break-words bg-muted/50 p-2 rounded">
                {error?.toString() || 'Unknown error'}
              </p>
            </div>
          </div>

          <div className="flex gap-2">
            <Button onClick={onReset} variant="default" className="flex-1">
              <RefreshCw className="w-4 h-4 mr-2" />
              Coba Lagi
            </Button>
            <Button onClick={onGoHome} variant="outline" className="flex-1">
              <Home className="w-4 h-4 mr-2" />
              Dashboard
            </Button>
          </div>
        </GlassCard>
      </div>
    );
  }

  // Module level (compact error)
  return (
    <div className="p-6">
      <GlassCard className="p-4 border-l-4 border-l-red-500">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-foreground mb-1">Module Error</h3>
            <p className="text-xs text-muted-foreground mb-3">
              {error?.toString() || 'Unknown error'}
            </p>
            <Button onClick={onReset} size="sm" variant="outline">
              <RefreshCw className="w-3 h-3 mr-2" />
              Coba Lagi
            </Button>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}

export default ErrorBoundary;
