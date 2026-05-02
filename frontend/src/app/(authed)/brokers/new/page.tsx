"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Eye,
  EyeOff,
  Loader2,
  PlugZap,
  ShieldAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "@/components/ui/toaster";
import { useCreateBroker, useTestBroker } from "@/lib/hooks/use-brokers";
import { ApiError } from "@/lib/api/client";
import {
  type BrokerCredentialsMT5,
  type BrokerCredentialsOANDA,
} from "@/lib/api/broker";
import type { BrokerType, BrokerTestResult } from "@/types/api";
import { formatCurrency } from "@/lib/utils/format";

const labelField = z.string().trim().min(1, "Label is required").max(64);

const oandaSchema = z.object({
  account_label: labelField,
  account_id: z.string().trim().min(1, "Account ID is required").max(64),
  api_token: z.string().trim().min(1, "API token is required"),
  environment: z.enum(["practice", "live"]),
});
type OandaForm = z.infer<typeof oandaSchema>;

const mt5Schema = z.object({
  account_label: labelField,
  account: z.coerce.number().int().positive("MT5 login must be a positive integer"),
  password: z.string().min(1, "Password is required"),
  server: z.string().trim().min(1, "Server is required").max(128),
});
type Mt5Form = z.infer<typeof mt5Schema>;

export default function NewBrokerPage() {
  const router = useRouter();
  const [step, setStep] = useState<"pick" | "form">("pick");
  const [type, setType] = useState<BrokerType | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="mb-2">
          <Link href="/brokers">
            <ArrowLeft className="h-4 w-4" /> Back to brokers
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">Connect a broker</h1>
        <p className="text-sm text-muted-foreground">
          Credentials are encrypted at rest with libsodium and never leave the server.
        </p>
      </div>

      {step === "pick" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <BrokerPickerCard
            label="OANDA"
            description="REST API · practice or live · v20"
            onClick={() => {
              setType("OANDA");
              setStep("form");
            }}
          />
          <BrokerPickerCard
            label="MetaTrader 5"
            description="Exness or other MT5 broker · login + server"
            onClick={() => {
              setType("MT5");
              setStep("form");
            }}
            note="Phase 2 runs in TEST_MODE on the Linux host — test will return canned data."
          />
        </div>
      )}

      {step === "form" && type === "OANDA" && (
        <OandaForm
          onCancel={() => {
            setType(null);
            setStep("pick");
          }}
          onSaved={(id) => router.push(`/brokers/${id}`)}
        />
      )}
      {step === "form" && type === "MT5" && (
        <Mt5Form
          onCancel={() => {
            setType(null);
            setStep("pick");
          }}
          onSaved={(id) => router.push(`/brokers/${id}`)}
        />
      )}
    </div>
  );
}

function BrokerPickerCard({
  label,
  description,
  note,
  onClick,
}: {
  label: string;
  description: string;
  note?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <Card className="h-full transition-colors hover:border-primary/40">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <PlugZap className="h-4 w-4" /> {label}
            </span>
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        {note && (
          <CardContent className="text-xs text-muted-foreground">{note}</CardContent>
        )}
      </Card>
    </button>
  );
}

// ---------- OANDA form ----------

function OandaForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: (id: string) => void }) {
  const form = useForm<OandaForm>({
    resolver: zodResolver(oandaSchema),
    defaultValues: { environment: "practice" } as Partial<OandaForm>,
  });
  const [showToken, setShowToken] = useState(false);
  const [testResult, setTestResult] = useState<BrokerTestResult | null>(null);
  const test = useTestBroker();
  const create = useCreateBroker();

  async function onTest(values: OandaForm) {
    setTestResult(null);
    try {
      const result = await test.mutateAsync({
        broker_type: "OANDA",
        credentials: {
          account_id: values.account_id,
          api_token: values.api_token,
          environment: values.environment,
        },
      });
      setTestResult(result);
      if (result.success) {
        toast.success("Connection OK", {
          description: `${result.account_currency ?? ""} balance ${formatCurrency(
            result.balance,
            result.account_currency ?? undefined,
          )}`,
        });
      } else {
        toast.error("Test failed", { description: result.error_message ?? result.error_code ?? "" });
      }
    } catch (err) {
      handleApiError(err);
    }
  }

  async function onSave(values: OandaForm) {
    try {
      const created = await create.mutateAsync({
        broker_type: "OANDA",
        account_label: values.account_label,
        credentials: {
          account_id: values.account_id,
          api_token: values.api_token,
          environment: values.environment,
        },
      });
      toast.success("Broker connected", { description: created.account_label });
      onSaved(created.id);
    } catch (err) {
      handleApiError(err);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">OANDA credentials</CardTitle>
        <CardDescription>Generate a token at OANDA → My Services → Manage API Access.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={form.handleSubmit(onSave)}>
          <FormField
            label="Account label"
            error={form.formState.errors.account_label?.message}
          >
            <Input placeholder="OANDA Practice" autoComplete="off" {...form.register("account_label")} />
          </FormField>
          <FormField label="Account ID" error={form.formState.errors.account_id?.message} hint="e.g. 101-001-12345678-001">
            <Input autoComplete="off" placeholder="101-001-…" {...form.register("account_id")} />
          </FormField>
          <FormField label="API token" error={form.formState.errors.api_token?.message}>
            <div className="relative">
              <Input
                type={showToken ? "text" : "password"}
                autoComplete="off"
                {...form.register("api_token")}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-1 top-1 h-8 w-8"
                onClick={() => setShowToken((s) => !s)}
                aria-label={showToken ? "Hide token" : "Show token"}
              >
                {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </FormField>
          <FormField label="Environment">
            <div className="flex gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="radio" value="practice" {...form.register("environment")} /> Practice
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" value="live" {...form.register("environment")} /> Live
              </label>
            </div>
          </FormField>

          <TestResultDisplay result={testResult} />

          <FormActions
            onCancel={onCancel}
            onTest={form.handleSubmit(onTest)}
            testing={test.isPending}
            saving={create.isPending}
            canSaveWithoutTest={Boolean(testResult?.success)}
          />
        </form>
      </CardContent>
    </Card>
  );
}

// ---------- MT5 form ----------

function Mt5Form({ onCancel, onSaved }: { onCancel: () => void; onSaved: (id: string) => void }) {
  const form = useForm<Mt5Form>({ resolver: zodResolver(mt5Schema) });
  const [showPwd, setShowPwd] = useState(false);
  const [testResult, setTestResult] = useState<BrokerTestResult | null>(null);
  const test = useTestBroker();
  const create = useCreateBroker();

  function buildCreds(values: Mt5Form): BrokerCredentialsMT5 {
    return {
      account: values.account,
      password: values.password,
      server: values.server,
    };
  }

  async function onTest(values: Mt5Form) {
    setTestResult(null);
    try {
      const result = await test.mutateAsync({ broker_type: "MT5", credentials: buildCreds(values) });
      setTestResult(result);
      if (result.success) {
        toast.success("Connection OK", { description: `Account ${result.account_number}` });
      } else {
        toast.error("Test failed", { description: result.error_message ?? "" });
      }
    } catch (err) {
      handleApiError(err);
    }
  }

  async function onSave(values: Mt5Form) {
    try {
      const created = await create.mutateAsync({
        broker_type: "MT5",
        account_label: values.account_label,
        credentials: buildCreds(values),
      });
      toast.success("Broker connected", { description: created.account_label });
      onSaved(created.id);
    } catch (err) {
      handleApiError(err);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">MetaTrader 5 credentials</CardTitle>
        <CardDescription>
          MT5 runs in TEST_MODE on this Linux host — Phase 4 will wire a real Windows runner.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={form.handleSubmit(onSave)}>
          <FormField label="Account label" error={form.formState.errors.account_label?.message}>
            <Input placeholder="Exness Demo" {...form.register("account_label")} />
          </FormField>
          <FormField label="Login" error={form.formState.errors.account?.message} hint="MT5 numeric login">
            <Input
              type="number"
              inputMode="numeric"
              autoComplete="off"
              {...form.register("account", { valueAsNumber: true })}
            />
          </FormField>
          <FormField label="Password" error={form.formState.errors.password?.message}>
            <div className="relative">
              <Input
                type={showPwd ? "text" : "password"}
                autoComplete="off"
                {...form.register("password")}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-1 top-1 h-8 w-8"
                onClick={() => setShowPwd((s) => !s)}
                aria-label={showPwd ? "Hide password" : "Show password"}
              >
                {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
          </FormField>
          <FormField label="Server" error={form.formState.errors.server?.message} hint="e.g. Exness-MT5Trial11">
            <Input autoComplete="off" {...form.register("server")} />
          </FormField>

          <TestResultDisplay result={testResult} />

          <FormActions
            onCancel={onCancel}
            onTest={form.handleSubmit(onTest)}
            testing={test.isPending}
            saving={create.isPending}
            canSaveWithoutTest={Boolean(testResult?.success)}
          />
        </form>
      </CardContent>
    </Card>
  );
}

// ---------- shared bits ----------

function FormField({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  const id = label.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

function TestResultDisplay({ result }: { result: BrokerTestResult | null }) {
  if (!result) return null;
  if (result.success) {
    return (
      <Alert variant="success">
        <CheckCircle2 className="h-4 w-4" />
        <AlertTitle>Connection OK</AlertTitle>
        <AlertDescription className="space-y-0.5 text-sm">
          <div>Account {result.account_number}</div>
          <div>
            Balance {formatCurrency(result.balance, result.account_currency ?? undefined)} ·
            Equity {formatCurrency(result.equity, result.account_currency ?? undefined)}
          </div>
          <div className="text-xs">{result.server}</div>
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert variant="destructive">
      <ShieldAlert className="h-4 w-4" />
      <AlertTitle>Test failed</AlertTitle>
      <AlertDescription>
        {result.error_message ?? result.error_code ?? "Unknown error"}
      </AlertDescription>
    </Alert>
  );
}

function FormActions({
  onCancel,
  onTest,
  testing,
  saving,
  canSaveWithoutTest,
}: {
  onCancel: () => void;
  onTest: () => void;
  testing: boolean;
  saving: boolean;
  canSaveWithoutTest: boolean;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
      <Button type="button" variant="outline" onClick={onCancel}>
        Cancel
      </Button>
      <Button type="button" variant="secondary" onClick={onTest} disabled={testing || saving}>
        {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        Test connection
      </Button>
      <Button type="submit" disabled={saving || testing || !canSaveWithoutTest}>
        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
        Save broker
      </Button>
    </div>
  );
}

function handleApiError(err: unknown) {
  if (err instanceof ApiError) {
    if (err.status === 429) {
      toast.error("Rate limited", {
        description: err.retryAfterSeconds
          ? `Retry in ${err.retryAfterSeconds}s`
          : "Please wait a moment and try again.",
      });
      return;
    }
    if (err.status === 422) {
      toast.error("Validation failed", { description: err.message });
      return;
    }
    toast.error(`Request failed (${err.status})`, {
      description: err.requestId ? `request_id: ${err.requestId}` : err.message,
    });
    return;
  }
  toast.error("Unexpected error");
}
