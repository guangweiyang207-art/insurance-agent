import {
  CustomerServiceOutlined,
  LoginOutlined,
  SafetyCertificateOutlined,
  UserAddOutlined,
} from '@ant-design/icons';
import { Alert, Button, Empty, Modal, Segmented, Skeleton } from 'antd';
import { useEffect, useState } from 'react';

import { listProducts } from './api';
import { AuthModal } from './AuthModal';
import { CATEGORY_LABELS } from './categoryLabels';
import { ProductCard } from './ProductCard';
import type { AuthMode, AuthSession, InsuranceCategory, Product } from './types';

type CategoryFilter = InsuranceCategory | 'all';

const CATEGORY_OPTIONS: Array<{ label: string; value: CategoryFilter }> = [
  { label: '全部', value: 'all' },
  { label: '医疗险', value: 'medical' },
  { label: '重疾险', value: 'critical_illness' },
  { label: '寿险', value: 'life' },
  { label: '意外险', value: 'accident' },
];

interface HomePageProps {
  session: AuthSession | null;
  initialAuthMode?: AuthMode | null;
  onAuthenticated: (session: AuthSession) => void;
  onLogout: () => void;
  onConsult: () => void;
}

export function HomePage({
  session,
  initialAuthMode = null,
  onAuthenticated,
  onLogout,
  onConsult,
}: HomePageProps) {
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>(initialAuthMode ?? 'login');
  const [authOpen, setAuthOpen] = useState(initialAuthMode !== null);
  const [consultAfterLogin, setConsultAfterLogin] = useState(initialAuthMode !== null);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    listProducts(category, controller.signal)
      .then((page) => setProducts(page.items))
      .catch((reason) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') return;
        setError(reason instanceof Error ? reason.message : '产品加载失败');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [category, reloadKey]);

  function openAuth(mode: AuthMode, continueToAdvisor = false) {
    setAuthMode(mode);
    setConsultAfterLogin(continueToAdvisor);
    setAuthOpen(true);
  }

  function consult() {
    if (session) {
      onConsult();
      return;
    }
    openAuth('login', true);
  }

  function authenticated(nextSession: AuthSession) {
    onAuthenticated(nextSession);
    setAuthOpen(false);
    if (consultAfterLogin) onConsult();
    setConsultAfterLogin(false);
  }

  return (
    <div className="page-shell">
      <header className="site-header">
        <div className="site-header__inner">
          <a className="brand" href="/" aria-label="安心保首页">
            <span className="brand__mark"><SafetyCertificateOutlined /></span>
            <span><strong>安心保</strong><small>保险优选平台</small></span>
          </a>
          <nav className="site-nav" aria-label="主导航">
            <a className="is-active" href="#products">保险产品</a>
            <a href="#service">服务保障</a>
          </nav>
          <div className="site-actions">
            {session ? (
              <>
                <span className="user-name">{session.user.displayName || session.user.username}</span>
                <Button type="text" onClick={onLogout}>退出</Button>
              </>
            ) : (
              <>
                <Button type="text" icon={<LoginOutlined />} onClick={() => openAuth('login')}>
                  登录
                </Button>
                <Button icon={<UserAddOutlined />} onClick={() => openAuth('register')}>
                  注册
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        <section className="intro-band">
          <div>
            <h1>选对保障，更从容地面对生活</h1>
            <p>汇集多家保险公司产品，按需求清晰比较，保费以实际试算结果为准。</p>
          </div>
          <Button type="primary" ghost icon={<CustomerServiceOutlined />} onClick={consult}>
            让顾问帮我选
          </Button>
        </section>

        <section className="products-section" id="products">
          <div className="products-heading">
            <div>
              <h2>保险产品</h2>
              <p>根据保障需求选择合适的产品类型</p>
            </div>
            <span>{loading ? '正在加载' : `共 ${products.length} 款产品`}</span>
          </div>
          <div className="category-filter" aria-label="按保险类型筛选">
            <Segmented<CategoryFilter>
              value={category}
              options={CATEGORY_OPTIONS}
              onChange={setCategory}
            />
          </div>

          {error ? (
            <Alert
              className="products-alert"
              type="error"
              showIcon
              message="产品加载失败"
              description={error}
              action={<Button onClick={() => setReloadKey((value) => value + 1)}>重新加载</Button>}
            />
          ) : null}

          {loading ? (
            <div className="product-grid" aria-label="产品加载中">
              {Array.from({ length: 6 }, (_, index) => (
                <div className="product-skeleton" key={index}><Skeleton active /></div>
              ))}
            </div>
          ) : products.length ? (
            <div className="product-grid">
              {products.map((product) => (
                <ProductCard key={product.id} product={product} onView={setSelectedProduct} />
              ))}
            </div>
          ) : (
            <Empty description="该类型暂时没有可展示的产品" />
          )}
        </section>

        <section className="service-strip" id="service">
          <div><strong>多家产品</strong><span>覆盖常见保障需求</span></div>
          <div><strong>信息清晰</strong><span>条款重点集中展示</span></div>
          <div><strong>顾问协助</strong><span>按预算和需求组合建议</span></div>
        </section>
      </main>

      <footer className="site-footer">保险产品信息仅供参考，具体保障责任以保险合同和实际投保页面为准。</footer>

      <AuthModal
        open={authOpen}
        mode={authMode}
        onModeChange={setAuthMode}
        onCancel={() => {
          setAuthOpen(false);
          setConsultAfterLogin(false);
        }}
        onSuccess={authenticated}
      />

      <Modal
        open={selectedProduct !== null}
        title={selectedProduct?.name}
        footer={[
          <Button key="close" onClick={() => setSelectedProduct(null)}>关闭</Button>,
          <Button key="consult" type="primary" onClick={consult}>咨询顾问</Button>,
        ]}
        onCancel={() => setSelectedProduct(null)}
        width={620}
      >
        {selectedProduct ? (
          <div className="product-detail">
            <p>{selectedProduct.description}</p>
            <dl>
              <div><dt>承保公司</dt><dd>{selectedProduct.insurer}</dd></div>
              <div><dt>保险类型</dt><dd>{CATEGORY_LABELS[selectedProduct.category]}</dd></div>
              <div><dt>适合人群</dt><dd>{selectedProduct.target_group}</dd></div>
              <div><dt>保费参考</dt><dd>¥{selectedProduct.min_premium.toLocaleString('zh-CN')} 起/年</dd></div>
            </dl>
            <h4>产品亮点</h4>
            <ul>{selectedProduct.highlights.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
