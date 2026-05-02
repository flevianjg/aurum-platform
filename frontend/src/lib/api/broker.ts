import { api } from "@/lib/api/client";
import type {
  BrokerAccount,
  BrokerAccountDetail,
  BrokerTestResult,
  BrokerType,
} from "@/types/api";

export interface BrokerCredentialsMT5 {
  account: number;
  password: string;
  server: string;
}

export interface BrokerCredentialsOANDA {
  account_id: string;
  api_token: string;
  environment: "practice" | "live";
}

export type BrokerCredentials = BrokerCredentialsMT5 | BrokerCredentialsOANDA;

export interface BrokerTestRequest {
  broker_type: BrokerType;
  credentials: BrokerCredentials;
}

export interface BrokerConnectRequest extends BrokerTestRequest {
  account_label: string;
}

export const brokerApi = {
  test(req: BrokerTestRequest) {
    return api<BrokerTestResult>("/broker/test", { method: "POST", json: req });
  },
  connect(req: BrokerConnectRequest) {
    return api<BrokerAccount>("/broker", { method: "POST", json: req });
  },
  list() {
    return api<BrokerAccount[]>("/broker");
  },
  read(id: string) {
    return api<BrokerAccountDetail>(`/broker/${id}`);
  },
  testStored(id: string) {
    return api<BrokerTestResult>(`/broker/${id}/test`, { method: "POST" });
  },
  deactivate(id: string) {
    return api<BrokerAccount>(`/broker/${id}/deactivate`, { method: "PATCH" });
  },
  reactivate(id: string) {
    return api<BrokerAccount>(`/broker/${id}/reactivate`, { method: "PATCH" });
  },
  remove(id: string) {
    return api<void>(`/broker/${id}`, { method: "DELETE" });
  },
};
