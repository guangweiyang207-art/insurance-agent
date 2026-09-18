import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  FileTextOutlined,
  HeartOutlined,
  IdcardOutlined,
  PayCircleOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Alert, Button, Steps } from 'antd';
import { useEffect, useState } from 'react';

import { ApiError, markPlanItemInsured } from './api';
import type { AuthSession } from './types';

interface ApplicationPageProps {
  session: AuthSession;
  onBack: () => void;
  onSessionExpired: () => void;
}

const APPLICATION_STEPS = [
  { title: '保费试算', icon: <PayCircleOutlined /> },
  { title: '客户告知', icon: <FileTextOutlined /> },
  { title: '健康告知', icon: <HeartOutlined /> },
  { title: '保单信息', icon: <IdcardOutlined /> },
  { title: '确认支付', icon: <CheckCircleOutlined /> },
];

export function ApplicationPage({ session, onBack, onSessionExpired }: ApplicationPageProps) {
  const params = new URLSearchParams(window.location.search);
  const productId = params.get('product_id');
  const planId = params.get('plan_id');
  const itemId = params.get('item_id');
  const [currentStep, setCurrentStep] = useState(0);
  const [paying, setPaying] = useState(false);
  const [paid, setPaid] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session.access_token) onSessionExpired();
  }, [onSessionExpired, session.access_token]);

  if (!session.access_token) {
    return null;
  }

  async function pay() {
    if (!planId || !itemId || paying || paid) return;
    setPaying(true);
    setError(null);
    try {
      await markPlanItemInsured(session.access_token, planId, itemId);
      setPaid(true);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        onSessionExpired();
        return;
      }
      setError(reason instanceof Error ? reason.message : '支付失败，请稍后重试');
    } finally {
      setPaying(false);
    }
  }

  const isLastStep = currentStep === APPLICATION_STEPS.length - 1;

  return (
    <div className="application-page">
      <header className="advisor-header">
        <div className="brand">
          <span className="brand__mark"><SafetyCertificateOutlined /></span>
          <span><strong>安心保</strong><small>投保流程</small></span>
        </div>
        <div>
          <span>{session.user.displayName || session.user.username}</span>
          <Button icon={<ArrowLeftOutlined />} onClick={onBack}>返回顾问</Button>
        </div>
      </header>

      <main className="application-shell">
        <section className="application-header">
          <div>
            <span>当前产品</span>
            <h1>{productId ? `产品 ID：${productId}` : '未选择产品'}</h1>
            <p>投保以页面流程为主，顾问负责解释条款、填写项和注意事项。</p>
          </div>
        </section>

        <section className="application-flow">
          <Steps current={paid ? APPLICATION_STEPS.length : currentStep} items={APPLICATION_STEPS} />
          {error ? <Alert showIcon type="error" message={error} /> : null}
          {paid ? (
            <Alert
              showIcon
              type="success"
              message="投保成功"
              description="保单状态已更新为投保成功，后续可以在理赔演示中查询到这份保单。"
            />
          ) : (
            <div className="application-step-body">
              <h2>{APPLICATION_STEPS[currentStep].title}</h2>
              <p>演示版本暂不填写本步骤内容，点击按钮直接进入下一步。</p>
              {!planId || !itemId ? (
                <Alert
                  showIcon
                  type="warning"
                  message="缺少方案项信息"
                  description="当前入口没有携带 plan_id 或 item_id，无法在支付后更新投保状态。请从保险方案产品卡片进入投保流程。"
                />
              ) : null}
              <div className="application-actions">
                {currentStep > 0 ? (
                  <Button onClick={() => setCurrentStep((step) => step - 1)}>上一步</Button>
                ) : null}
                {isLastStep ? (
                  <Button
                    type="primary"
                    icon={<PayCircleOutlined />}
                    loading={paying}
                    disabled={!planId || !itemId}
                    onClick={() => void pay()}
                  >
                    支付
                  </Button>
                ) : (
                  <Button type="primary" onClick={() => setCurrentStep((step) => step + 1)}>
                    下一步
                  </Button>
                )}
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
