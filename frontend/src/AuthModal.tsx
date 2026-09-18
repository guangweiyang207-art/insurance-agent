import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Form, Input, Modal, Segmented } from 'antd';
import { useEffect, useState } from 'react';

import { login, register } from './api';
import type { AuthMode, AuthSession } from './types';

interface AuthModalProps {
  open: boolean;
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;
  onCancel: () => void;
  onSuccess: (session: AuthSession) => void;
}

interface AuthFormValues {
  username: string;
  email?: string;
  password: string;
}

export function AuthModal({
  open,
  mode,
  onModeChange,
  onCancel,
  onSuccess,
}: AuthModalProps) {
  const [form] = Form.useForm<AuthFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    form.resetFields();
    setError(null);
  }, [form, mode, open]);

  async function submit(values: AuthFormValues) {
    setSubmitting(true);
    setError(null);
    try {
      const session =
        mode === 'login'
          ? await login(values.username, values.password)
          : await register(values.username, values.email ?? '', values.password);
      onSuccess(session);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '请求失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={null}
      footer={null}
      width={420}
      onCancel={onCancel}
      destroyOnHidden
      centered
    >
      <div className="auth-modal__header">
        <h2>欢迎来到安心保</h2>
        <p>登录后可使用智能顾问服务</p>
      </div>
      <Segmented<AuthMode>
        block
        value={mode}
        options={[
          { label: '登录', value: 'login' },
          { label: '注册', value: 'register' },
        ]}
        onChange={onModeChange}
      />
      {error ? <Alert className="auth-modal__alert" message={error} type="error" showIcon /> : null}
      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        <Form.Item
          label="用户名"
          name="username"
          rules={[{ required: true, message: '请输入用户名' }]}
        >
          <Input prefix={<UserOutlined />} placeholder="请输入用户名" size="large" />
        </Form.Item>
        {mode === 'register' ? (
          <Form.Item
            label="邮箱"
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="name@example.com" size="large" />
          </Form.Item>
        ) : null}
        <Form.Item
          label="密码"
          name="password"
          rules={[{ required: true, min: 6, message: '密码至少需要 6 位' }]}
        >
          <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" size="large" />
        </Form.Item>
        <button className="auth-submit" type="submit" disabled={submitting}>
          {submitting ? '提交中…' : mode === 'login' ? '登录' : '创建账号'}
        </button>
      </Form>
    </Modal>
  );
}
