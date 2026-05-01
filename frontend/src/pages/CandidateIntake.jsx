import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates } from "../api.js";
import { GeneratingScreen, Pillar } from "../components/Widgets.jsx";

// Role families and seniority levels must match backend lib/role_families.py
const ROLE_FAMILIES = [
  { value: "financial_analyst",  label: "Financial Analyst" },
  { value: "software_engineer",  label: "Software Engineer" },
  { value: "product_manager",    label: "Product Manager" },
  { value: "data_scientist",     label: "Data Scientist" },
  { value: "operations_manager", label: "Operations Manager" },
  { value: "marketing_manager",  label: "Marketing Manager" },
  { value: "sales_executive",    label: "Sales Executive" },
  { value: "hr_business_partner", label: "HR Business Partner" },
  { value: "legal_counsel",      label: "Legal Counsel" },
  { value: "strategy_consultant", label: "Strategy Consultant" },
];

const SENIORITY_LEVELS = [
  { value: "junior", label: "Junior (0–2 yrs)" },
  { value: "mid",    label: "Mid-level (2–5 yrs)" },
  { value: "senior", label: "Senior (5–9 yrs)" },
  { value: "lead",   label: "Lead / Principal (9+ yrs)" },
];

export default function CandidateIntake() {
  const nav = useNavigate();
  // steps: intro → target → bfi → sjt → submitting → submitted
  const [step, setStep] = useState("intro");
  const [instruments, setInstruments] = useState(null);
  const [targetRoleFamily, setTargetRoleFamily] = useState("");
  const [targetSeniority, setTargetSeniority] = useState("");
  const [bfiResponses, setBfiResponses] = useState({});
  const [sjtResponses, setSjtResponses] = useState({});
  const [error, setError] = useState("");

  useEffect(() => {
    candidates.getInstruments().then(setInstruments).catch((e) => setError(e.message));
  }, []);

  async function submit() {
    setStep("submitting");
    setError("");
    try {
      await candidates.submitAssessment({
        bfi_responses: bfiResponses,
        sjt_responses: sjtResponses,
        target_role_family: targetRoleFamily || null,
        target_seniority: targetSeniority || null,
      });
      setStep("submitted");
    } catch (e) {
      setError(e.message);
      setStep("sjt");
    }
  }

  if (error && !instruments) {
    return (
      <main className="container">
        <div className="label-mono" style={{ color: COLORS.accent }}>Error loading intake</div>
        <p>{error}</p>
      </main>
    );
  }

  if (!instruments && step !== "submitted") {
    return <GeneratingScreen note="Loading instrument…" />;
  }

  return (
    <main className="container" style={{ maxWidth: 860 }}>
      {step === "intro" && <IntroScreen onStart={() => setStep("target")} />}
      {step === "target" && (
        <TargetScreen
          roleFamily={targetRoleFamily}
          seniority={targetSeniority}
          setRoleFamily={setTargetRoleFamily}
          setSeniority={setTargetSeniority}
          onSubmit={() => setStep("bfi")}
        />
      )}
      {step === "bfi" && (
        <BfiScreen
          items={instruments.bfi}
          responses={bfiResponses}
          setResponses={setBfiResponses}
          onSubmit={() => setStep("sjt")}
        />
      )}
      {step === "sjt" && (
        <SjtScreen
          sjts={instruments.sjts}
          responses={sjtResponses}
          setResponses={setSjtResponses}
          onSubmit={submit}
          error={error}
        />
      )}
      {step === "submitting" && <GeneratingScreen note="Submitting your responses…" />}
      {step === "submitted" && <SubmittedScreen onContinue={() => nav("/dashboard")} />}
    </main>
  );
}

// ----------------------------------------------------------------------------
function IntroScreen({ onStart }) {
  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 16 }}>Candidate Intake</div>
      <h1
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 56,
          fontWeight: 500,
          lineHeight: 1.1,
          letterSpacing: "-0.02em",
          margin: "0 0 32px",
        }}
      >
        Before you try to impress anyone, tell us who you actually are.
      </h1>
      <p className="drop-cap" style={{ fontSize: 19, lineHeight: 1.65, marginBottom: 20 }}>
        You will not be told which companies you're being considered for. This is deliberate.
        When candidates know the target, they tailor. When they tailor, the signal degrades.
        We evaluate how you'd behave inside a company's actual environment — not how you
        present yourself against a job description.
      </p>
      <p style={{ fontSize: 17, marginBottom: 20, color: COLORS.muted }}>
        The assessment takes about twelve minutes. You'll answer ten short personality
        items and three situational judgment scenarios. We synthesize a behavioral persona
        and run it against the company environments in our template library. If there's a
        match, both you and the hiring manager are notified. Either party can decline
        without explanation.
      </p>
      <hr className="rule" style={{ margin: "40px 0" }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 32, marginBottom: 48 }}>
        <Pillar n="I" title="Environmental fit" body="Simulation against specific company artifacts, not generic trait norms." />
        <Pillar n="II" title="Blind to both sides" body="You don't know which companies. They don't see your profile until match." />
        <Pillar n="III" title="Auditable" body="Every score decomposes to the artifact text and persona signal that produced it." />
      </div>
      <button className="primary" onClick={onStart}>
        Begin intake →
      </button>
    </div>
  );
}

// ----------------------------------------------------------------------------
function TargetScreen({ roleFamily, seniority, setRoleFamily, setSeniority, onSubmit }) {
  const canContinue = roleFamily && seniority;
  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 12 }}>Step 1 of 3 · Target role</div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 34,
          fontWeight: 500,
          letterSpacing: "-0.01em",
          margin: "0 0 12px",
        }}
      >
        What kind of role are you looking for?
      </h2>
      <p style={{ color: COLORS.muted, marginBottom: 40, fontSize: 16 }}>
        We use this to find open positions that match your target. You will not be told
        which companies are considering you — that information stays blind until both sides opt in.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 40 }}>
        <div>
          <label className="label-mono" style={{ display: "block", marginBottom: 8 }}>
            Role family
          </label>
          <select
            className="ed"
            value={roleFamily}
            onChange={(e) => setRoleFamily(e.target.value)}
            style={{ width: "100%" }}
          >
            <option value="">— select —</option>
            {ROLE_FAMILIES.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="label-mono" style={{ display: "block", marginBottom: 8 }}>
            Seniority level
          </label>
          <select
            className="ed"
            value={seniority}
            onChange={(e) => setSeniority(e.target.value)}
            style={{ width: "100%" }}
          >
            <option value="">— select —</option>
            {SENIORITY_LEVELS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
      </div>

      <button className="primary" disabled={!canContinue} onClick={onSubmit}>
        Continue to assessment →
      </button>
    </div>
  );
}

// ----------------------------------------------------------------------------
function BfiScreen({ items, responses, setResponses, onSubmit }) {
  const complete = Object.keys(responses).length;
  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Step 2 of 3 · Big Five Inventory (BFI-10)
      </div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 34,
          fontWeight: 500,
          letterSpacing: "-0.01em",
          margin: "0 0 12px",
        }}
      >
        Ten items. Answer honestly — not strategically.
      </h2>
      <p style={{ color: COLORS.muted, marginBottom: 32, fontSize: 16 }}>
        Rate each statement from 1 (strongly disagree) to 5 (strongly agree). The validated
        BFI-10 is deliberately short; social-desirability bias is managed by cross-validation
        in Section II rather than by lengthening this section.
      </p>
      {items.map((item, idx) => (
        <div key={item.id} style={{ padding: "20px 0", borderBottom: `1px solid ${COLORS.rule}` }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 12 }}>
            <div className="label-mono" style={{ minWidth: 28 }}>
              {String(idx + 1).padStart(2, "0")}
            </div>
            <div style={{ fontSize: 17, flex: 1 }}>{item.text}</div>
          </div>
          <div className="likert" style={{ marginLeft: 44 }}>
            {[1, 2, 3, 4, 5].map((v) => (
              <button
                key={v}
                className={responses[item.id] === v ? "selected" : ""}
                onClick={() => setResponses({ ...responses, [item.id]: v })}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
      ))}
      <div style={{ marginTop: 40, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="label-mono">{complete} of {items.length} answered</div>
        <button className="primary" disabled={complete < items.length} onClick={onSubmit}>
          Continue to scenarios →
        </button>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
function SjtScreen({ sjts, responses, setResponses, onSubmit, error }) {
  const complete = Object.keys(responses).length;
  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 12 }}>Step 3 of 3 · Situational Judgment</div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 34,
          fontWeight: 500,
          letterSpacing: "-0.01em",
          margin: "0 0 12px",
        }}
      >
        Three scenarios. Pick the option closest to what you would actually do.
      </h2>
      <p style={{ color: COLORS.muted, marginBottom: 40, fontSize: 16 }}>
        Not what you think sounds best. These scenarios are drawn from the daily texture of
        analyst work in environments where models are treated as arguments and disagreement
        is part of the job.
      </p>
      {sjts.map((sjt, idx) => (
        <div
          key={sjt.id}
          style={{ marginBottom: 48, paddingBottom: 32, borderBottom: `1px solid ${COLORS.rule}` }}
        >
          <div className="label-mono" style={{ marginBottom: 12 }}>Scenario {idx + 1}</div>
          <p
            style={{
              fontSize: 18,
              lineHeight: 1.6,
              fontStyle: "italic",
              color: COLORS.ink,
              marginBottom: 20,
              borderLeft: `3px solid ${COLORS.accent}`,
              paddingLeft: 20,
            }}
          >
            {sjt.scenario}
          </p>
          <p style={{ fontSize: 17, fontWeight: 500, marginBottom: 16 }}>{sjt.question}</p>
          {sjt.options.map((opt) => (
            <button
              key={opt.id}
              className={`choice ${responses[sjt.id] === opt.id ? "selected" : ""}`}
              onClick={() => setResponses({ ...responses, [sjt.id]: opt.id })}
            >
              <span style={{ fontFamily: FONT_MONO, fontSize: 12, opacity: 0.6, marginRight: 12 }}>
                {opt.id.toUpperCase()}
              </span>
              {opt.text}
            </button>
          ))}
        </div>
      ))}
      {error && (
        <div style={{ color: COLORS.accent, marginBottom: 16, fontStyle: "italic" }}>{error}</div>
      )}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="label-mono">{complete} of {sjts.length} answered</div>
        <button className="primary" disabled={complete < sjts.length} onClick={onSubmit}>
          Submit responses →
        </button>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
function SubmittedScreen({ onContinue }) {
  return (
    <div style={{ padding: "80px 0" }}>
      <div className="label-mono" style={{ marginBottom: 16 }}>Submitted</div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 44,
          fontWeight: 500,
          letterSpacing: "-0.015em",
          lineHeight: 1.1,
          margin: "0 0 16px",
        }}
      >
        Your responses are in.
      </h2>
      <p className="drop-cap" style={{ fontSize: 18, lineHeight: 1.65, marginBottom: 16 }}>
        Your evaluation is running against any open positions that match your target role
        and seniority. You will not be told which companies are involved. If there's a
        mutual interest, you'll see an invitation on your profile to opt in or decline —
        and neither side knows who's on the other until both agree.
      </p>
      <button className="primary" onClick={onContinue}>Go to my dashboard →</button>
    </div>
  );
}
