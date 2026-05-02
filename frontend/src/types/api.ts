// Mirrors selected backend response shapes. Keep in sync with backend/app/schemas.

export type UserRole = "OWNER" | "MEMBER" | "VIEWER";

export interface UserOut {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
}

export interface PasskeyChallengeResponse {
  challenge_id: string;
  publicKey: Record<string, unknown>;
}

export interface PasskeyRegisterFinishResponse {
  passkey_id: string;
}

export type BrokerType = "MT5" | "OANDA";

export interface BrokerAccount {
  id: string;
  broker_type: BrokerType;
  account_label: string;
  account_number: string | null;
  server: string | null;
  account_currency: string | null;
  is_active: boolean;
  last_tested_at: string | null;
  last_test_status: string | null;
  created_at: string;
}

export interface LiveAccountInfo {
  account_number: string;
  currency: string;
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  margin_level: number | null;
  server: string;
}

export interface BrokerAccountDetail extends BrokerAccount {
  last_test_error: string | null;
  live_account_info: LiveAccountInfo | null;
}

export interface BrokerTestResult {
  success: boolean;
  account_number: string | null;
  account_currency: string | null;
  server: string | null;
  balance: number | null;
  equity: number | null;
  error_code: string | null;
  error_message: string | null;
}

export interface ApiErrorBody {
  error: string;
  message: string;
  status: number;
  request_id?: string;
}

export interface PasskeyOut {
  id: string;
  nickname: string | null;
  transports: string[] | null;
  created_at: string;
  last_used_at: string | null;
}
