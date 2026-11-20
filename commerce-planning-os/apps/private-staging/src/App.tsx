import { useCallback, useEffect, useState } from 'react';
import { auth, api } from '@appdeploy/client';
import {
  ShieldCheck,
  RefreshCw,
  Database,
  LockKeyhole,
  Package,
  AlertCircle,
  LogOut,
} from 'lucide-react';

type Viewer = { email?: string; userId: string };
type Status = {
  authorized: boolean;
  configured: { ownerConfigured: boolean; shopifyConfigured: boolean };
  state: {
    synced: number;
    complete: boolean;
    updatedAt: string;
    status: string;
    sourceCount?: number;
  } | null;
};
type Product = {
  id: string;
  title: string;
  vendor: string;
  category: string;
  variants: {
    id: string;
    sku: string | null;
    price: string;
    stock: number | null;
  }[];
  fetchedAt: string;
};
function App() {
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [nextToken, setNextToken] = useState<string | null>(null);
  const [errorText, setErrorText] = useState('');
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const load = useCallback(async () => {
    try {
      const result = await api.get('/api/status');
      const current = result.data as Status;
      setStatus(current);
      if (current.authorized) {
        const rows = await api.get('/api/products');
        setProducts((rows.data.products || []) as Product[]);
        setNextToken(rows.data.nextToken || null);
      } else {
        setProducts([]);
      }
    } catch {
      setErrorText('無法讀取受保護的資料服務，請稍後重新載入。');
    }
  }, []);
  useEffect(() => {
    let active = true;
    auth
      .getUser()
      .then(u => {
        if (!active) return;
        setViewer(u ? { email: u.email, userId: u.userId } : null);
        setReady(true);
      })
      .catch(() => {
        if (active) {
          setReady(true);
          setErrorText('登入狀態確認失敗。');
        }
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (viewer) void load();
  }, [viewer, load]);
  const loadMore = async () => {
    if (!nextToken) return;
    try {
      const response = await api.get('/api/products', { params: { nextToken } });
      const following = (response.data.products || []) as Product[];
      setProducts(previous => {
        const ids = new Set(previous.map(item => item.id));
        return [...previous, ...following.filter(item => !ids.has(item.id))];
      });
      setNextToken(response.data.nextToken || null);
    } catch {
      setErrorText('無法載入下一頁商品，請重新整理後再試。');
    }
  };
  const signIn = async () => {
    setStarting(true);
    setErrorText('');
    try {
      await auth.signInWithRedirect();
    } catch {
      setErrorText('登入跳轉失敗，請確認瀏覽器允許儲存資料並重試。');
      setStarting(false);
    }
  };
  const signOut = async () => {
    await auth.signOut();
    setViewer(null);
    setStatus(null);
    setProducts([]);
  };
  const sync = async () => {
    setBusy(true);
    setErrorText('');
    try {
      await api.post('/api/sync', {});
      await load();
    } catch {
      setErrorText(
        '同步未完成。請檢查唯讀憑證、商店權限或服務狀態，游標不會前進。'
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="shell">
      <header>
        <div className="brand">
          <div className="mark">
            <Database size={22} />
          </div>
          <div>
            <strong>Commerce Planning OS</strong>
            <small>P1 · PRIVATE INTEGRATION STAGING</small>
          </div>
        </div>
        {viewer ? (
          <button className="quiet" onClick={signOut}>
            <LogOut size={16} /> 登出
          </button>
        ) : (
          <span className="pill">受保護的測試環境</span>
        )}
      </header>
      <section className="intro">
        <p className="eyebrow">MERCHANDISE DATA FOUNDATION</p>
        <h1>Shopify 商品資料同步工作台</h1>
        <p>
          真實資料只在通過身分驗證、管理員核准及密鑰設定後，才會經後端唯讀同步。
        </p>
      </section>
      {!ready ? (
        <section className="panel">正在驗證登入狀態…</section>
      ) : !viewer ? (
        <section className="panel centered">
          <LockKeyhole size={34} />
          <h2>請先登入測試環境</h2>
          <p>商品、庫存與同步紀錄不對匿名訪客開放。</p>
          <button onClick={signIn} disabled={starting}>
            {starting ? '準備登入…' : '安全登入'}
          </button>
        </section>
      ) : !status?.authorized ? (
        <section className="panel centered">
          <ShieldCheck size={34} />
          <h2>帳號尚未被核准</h2>
          <p>
            已登入 {viewer.email || '使用者'}
            ，但目前沒有商品資料存取權。管理員須先完成核准帳號的加密設定。
          </p>
          <button onClick={() => void load()}>重新確認授權</button>
        </section>
      ) : (
        <>
          <div className="banner">
            <ShieldCheck size={18} />
            <span>
              已驗證管理員身分。Shopify 採唯讀 GraphQL；不會改動商店商品或庫存。
            </span>
          </div>
          <section className="cards">
            <article>
              <small>目標商店</small>
              <strong>DESCENTE TW</strong>
              <span>單商店隔離</span>
            </article>
            <article>
              <small>累積同步商品</small>
              <strong>{status.state?.synced ?? 0} / {status.state?.sourceCount ?? '待取得'}</strong>
              <span>
                {status.state?.complete
                  ? '已走訪至最後游標'
                  : '尚未完成全量同步'}
              </span>
            </article>
            <article>
              <small>同步紀錄</small>
              <strong>
                {status.state?.updatedAt
                  ? new Date(status.state.updatedAt).toLocaleString('zh-TW')
                  : '未開始'}
              </strong>
              <span>資料庫持續保存</span>
            </article>
          </section>
          <section className="panel">
            <div className="paneltop">
              <div>
                <h2>Shopify 唯讀同步</h2>
                <p>
                  每次最多同步 30 件商品，持續保存游標。全量對帳尚未完成時，不顯示為已驗證。
                </p>
              </div>
              <button
                disabled={busy || !status.configured.shopifyConfigured}
                onClick={sync}
              >
                <RefreshCw size={16} />
                {busy ? '同步中…' : '同步下一批'}
              </button>
            </div>
            <div className="checks">
              <div>
                <span>Shopify 唯讀憑證</span>
                <strong>
                  {status.configured.shopifyConfigured ? '已設定' : '尚未設定'}
                </strong>
              </div>
              <div>
                <span>同步資料驗證</span>
                <strong>{status.state?.status || '等待同步'}</strong>
              </div>
              <div>
                <span>全量來源對帳</span>
                <strong>{status.state?.status === 'source_count_matched_pending_audit' ? '筆數符合，待稽核' : '尚未通過'}</strong>
              </div>
            </div>
          </section>
          <section className="panel">
            <div className="paneltop">
              <div>
                <h2>商品與變體資料</h2>
                <p>僅限核准使用者查看。商品成本必須由獨立財務來源匯入。</p>
              </div>
              <Package size={22} />
            </div>
            {products.length === 0 ? (
              <div className="empty">
                目前沒有已同步商品。安全連線設定完成後，可從上方啟動同步。
              </div>
            ) : (
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th>商品</th>
                      <th>SKU</th>
                      <th>售價</th>
                      <th>庫存</th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.flatMap(p =>
                      p.variants.map(v => (
                        <tr key={v.id}>
                          <td>
                            <strong>{p.title}</strong>
                            <small>{p.vendor}</small>
                          </td>
                          <td>{v.sku || '未設定'}</td>
                          <td>{v.price}</td>
                          <td>{v.stock ?? '未知'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
                {nextToken && <button className='quiet' onClick={() => void loadMore()}>載入更多商品</button>}
              </div>
            )}
          </section>
        </>
      )}
      {errorText && (
        <div className="error">
          <AlertCircle size={18} />
          {errorText}
        </div>
      )}
      <footer>
        受保護的 P1 測試環境 · 真實資料啟用前需完成管理員核准、同步和來源對帳 ·
        永不寫回 Shopify
      </footer>
    </main>
  );
}
export default App;
