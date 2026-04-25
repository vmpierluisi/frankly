import React, { useState } from "react";

/* ============================================================================
   HIRING SIMULATION PLATFORM — v0 DEMO
   ============================================================================
   Architectural boundary: everything below the `runMatchingEngine` function
   is stable. That function is the ONLY thing that gets replaced when we move
   from demo to real product — swap the deterministic scoring for a single
   Claude API call with the prompt in `MATCHING_PROMPT`. Same input shape,
   same output shape. Everything else stays identical.

   v1 upgrade path:
     - runMatchingEngine      → Claude API call
     - SEED_COMPANIES         → sanctioned artifact ingestion
     - candidateProfile       → HrFlow Parsing API for real resumes
     - MiroFish               → replaces persona behavior simulation
     - ReasoningLayer         → wraps the final scoring call for audit trails
   ========================================================================= */

// ============================================================================
// FICTIONAL SEED COMPANY — FINANCIAL ANALYST ROLE
// In production: sanctioned artifacts uploaded by the hiring manager.
// ============================================================================
const SEED_COMPANIES = [
  {
    id: "meridian-capital",
    name: "Meridian Capital Partners",
    tagline: "Mid-market private credit. Amsterdam + NYC.",
    role: "Financial Analyst — Credit Underwriting",
    artifacts: {
      values: `We write checks on companies our competitors don't understand. Our edge is patience and homework, not speed. Analysts are expected to disagree with deal teams in writing, early, and often. We reward being right over being first. We do not reward hustle theatre.`,
      roleSpec: `Build and defend underwriting models for mid-market credit deals ($25M–$150M). Produce memos that hold up under IC scrutiny. Own your numbers end-to-end. Comfort with ambiguity and ability to say "I don't know yet" are prerequisites.`,
      teamStructure: `Flat team of 11. Two MDs, three VPs, four associates, two analysts. No hierarchy in credit debates — the model is the argument. Weekly deal review is the forum; memos circulate 48h prior. Red team rotates.`,
      sampleComms: `[IC memo excerpt] "Recommend PASS. Sponsor's thesis depends on 180bps of margin expansion driven by procurement synergies that have not been realized in any of their last four platforms. I've modeled three scenarios — see Appendix C — and none clear our 15% unlevered IRR hurdle without aggressive assumptions. Happy to walk through the sensitivity at Thursday's review."`
    },
    // Formal criteria derived from the artifacts. In production this comes
    // from the template setup flow (the "unsolved problem" in the brief).
    criteria: {
      analyticalRigor: { weight: 0.25, description: "Depth over speed; defends numbers" },
      intellectualHonesty: { weight: 0.25, description: "Comfortable saying 'I don't know'" },
      writtenDissent: { weight: 0.20, description: "Disagrees in writing, early, constructively" },
      ambiguityTolerance: { weight: 0.15, description: "Operates without clear playbooks" },
      lowEgoCollab: { weight: 0.15, description: "Model-as-argument, not status-as-argument" }
    }
  }
];

// ============================================================================
// PSYCHOMETRIC INSTRUMENTS — BFI-10 + 3 SJTs
// BFI-10 is the validated 10-item Big Five inventory (Rammstedt & John 2007).
// SJTs are custom, authored against the Meridian artifacts.
// ============================================================================
const BFI10 = [
  { id: "e1", text: "I see myself as someone who is reserved", trait: "E", reverse: true },
  { id: "a1", text: "I see myself as someone who is generally trusting", trait: "A", reverse: false },
  { id: "c1", text: "I see myself as someone who tends to be lazy", trait: "C", reverse: true },
  { id: "n1", text: "I see myself as someone who is relaxed, handles stress well", trait: "N", reverse: true },
  { id: "o1", text: "I see myself as someone who has few artistic interests", trait: "O", reverse: true },
  { id: "e2", text: "I see myself as someone who is outgoing, sociable", trait: "E", reverse: false },
  { id: "a2", text: "I see myself as someone who tends to find fault with others", trait: "A", reverse: true },
  { id: "c2", text: "I see myself as someone who does a thorough job", trait: "C", reverse: false },
  { id: "n2", text: "I see myself as someone who gets nervous easily", trait: "N", reverse: false },
  { id: "o2", text: "I see myself as someone who has an active imagination", trait: "O", reverse: false }
];

const SJTs = [
  {
    id: "sjt1",
    scenario: "You've spent six days modeling a deal the MD is clearly excited about. Your base case shows a 12% IRR — below the firm's 15% hurdle. The MD mentions in passing that 'there's always upside we haven't captured.' The IC memo is due tomorrow.",
    question: "What do you do?",
    options: [
      { id: "a", text: "Send the memo with the 12% base case and three downside scenarios. Flag the gap to the hurdle prominently.", signal: { intellectualHonesty: 5, writtenDissent: 5, analyticalRigor: 4 } },
      { id: "b", text: "Revisit assumptions to see if there's legitimate upside the MD might be pointing to, then send the memo reflecting whatever you find.", signal: { intellectualHonesty: 4, analyticalRigor: 5, writtenDissent: 3 } },
      { id: "c", text: "Adjust the growth assumption upward to reflect the MD's implied confidence, bringing IRR to 15.5%. Note the change in the memo.", signal: { intellectualHonesty: 1, writtenDissent: 1, analyticalRigor: 2 } },
      { id: "d", text: "Ask the MD directly what upside they see before finalizing the memo.", signal: { intellectualHonesty: 4, lowEgoCollab: 4, writtenDissent: 2 } }
    ]
  },
  {
    id: "sjt2",
    scenario: "In deal review, a VP publicly dismisses a risk you raised in your memo as 'theoretical.' You believe the risk is real and material. Five other people are in the room.",
    question: "What do you do?",
    options: [
      { id: "a", text: "Defend your position in the meeting with the specific data points from your sensitivity analysis.", signal: { writtenDissent: 5, analyticalRigor: 5, lowEgoCollab: 3 } },
      { id: "b", text: "Note it, move on, and follow up with the VP privately after the meeting.", signal: { writtenDissent: 2, lowEgoCollab: 4 } },
      { id: "c", text: "Acknowledge the VP's experience, but ask the room if anyone wants to walk through Appendix C before dismissing it.", signal: { writtenDissent: 4, lowEgoCollab: 5, analyticalRigor: 4 } },
      { id: "d", text: "Drop it — you've already put it in writing in the memo, which is what matters.", signal: { writtenDissent: 3, lowEgoCollab: 3 } }
    ]
  },
  {
    id: "sjt3",
    scenario: "You're asked to build a model for a sector you've never covered. You have three days. Your honest assessment after day one is that you don't understand the unit economics well enough to produce reliable numbers.",
    question: "What do you do?",
    options: [
      { id: "a", text: "Produce the model on schedule with clearly-flagged assumptions and caveats about your confidence level.", signal: { intellectualHonesty: 4, ambiguityTolerance: 4, analyticalRigor: 3 } },
      { id: "b", text: "Tell the deal lead on day two that you need a two-day extension and why.", signal: { intellectualHonesty: 5, ambiguityTolerance: 3, writtenDissent: 3 } },
      { id: "c", text: "Push through, build the best model you can, and present it as your best estimate.", signal: { intellectualHonesty: 2, ambiguityTolerance: 2 } },
      { id: "d", text: "Find two sector experts in the firm's network, burn a day on calls, then build the model with citations.", signal: { intellectualHonesty: 4, ambiguityTolerance: 5, analyticalRigor: 5, lowEgoCollab: 4 } }
    ]
  }
];

// ============================================================================
// PERSONA SYNTHESIS
// Maps BFI-10 + SJT responses into a behavioral persona. This is a simplified
// version of the "unsolved science" problem — in production, MiroFish handles
// the agent parameterization.
// ============================================================================
function synthesizePersona(bfiResponses, sjtResponses) {
  // BFI-10 scoring: average the two items per trait (reversed where needed)
  const traits = { O: [], C: [], E: [], A: [], N: [] };
  BFI10.forEach(item => {
    const raw = bfiResponses[item.id] ?? 3;
    const scored = item.reverse ? 6 - raw : raw;
    traits[item.trait].push(scored);
  });
  const bigFive = {
    openness:          avg(traits.O),
    conscientiousness: avg(traits.C),
    extraversion:      avg(traits.E),
    agreeableness:     avg(traits.A),
    neuroticism:       avg(traits.N)
  };

  // SJT signal aggregation
  const sjtSignals = {
    analyticalRigor: 0, intellectualHonesty: 0, writtenDissent: 0,
    ambiguityTolerance: 0, lowEgoCollab: 0
  };
  let sjtCount = 0;
  SJTs.forEach(sjt => {
    const chosenId = sjtResponses[sjt.id];
    if (!chosenId) return;
    const chosen = sjt.options.find(o => o.id === chosenId);
    if (!chosen) return;
    Object.entries(chosen.signal).forEach(([k, v]) => {
      if (sjtSignals[k] !== undefined) sjtSignals[k] += v;
    });
    sjtCount++;
  });
  // Normalize SJT signals to 1-5 scale (max possible per dimension ≈ 5 per SJT)
  Object.keys(sjtSignals).forEach(k => {
    sjtSignals[k] = sjtCount > 0 ? sjtSignals[k] / sjtCount : 0;
  });

  // Cross-validation: flag inconsistencies between self-reported and observed
  const inconsistencies = [];
  // Example: high agreeableness + high writtenDissent is unusual
  if (bigFive.agreeableness >= 4 && sjtSignals.writtenDissent >= 4) {
    inconsistencies.push({
      type: "agreeable-dissenter",
      note: "Self-reports high agreeableness but SJT responses indicate strong willingness to dissent in writing. Could be genuine (principled dissent within a cooperative disposition) or social-desirability bias in BFI. Worth probing in interview."
    });
  }
  if (bigFive.conscientiousness <= 2.5 && sjtSignals.analyticalRigor >= 4) {
    inconsistencies.push({
      type: "low-c-high-rigor",
      note: "Self-reports lower conscientiousness but SJT responses favor thorough analysis. May indicate domain-specific rigor vs general tidiness."
    });
  }
  if (bigFive.neuroticism >= 4 && sjtSignals.ambiguityTolerance >= 4) {
    inconsistencies.push({
      type: "neurotic-but-tolerant",
      note: "High neuroticism paired with high demonstrated ambiguity tolerance. Could indicate coping through structure rather than genuine comfort — worth probing."
    });
  }

  return {
    bigFive,
    sjtSignals,
    inconsistencies,
    // Behavioral summary — in production this is an LLM-generated narrative
    narrative: generateNarrative(bigFive, sjtSignals)
  };
}

function avg(arr) { return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0; }

function generateNarrative(bf, sjt) {
  const bits = [];
  if (bf.conscientiousness >= 4) bits.push("detail-oriented and thorough");
  else if (bf.conscientiousness <= 2.5) bits.push("favors velocity over exhaustiveness");
  if (bf.openness >= 4) bits.push("intellectually curious");
  if (bf.extraversion <= 2.5) bits.push("works deeply in solitude");
  else if (bf.extraversion >= 4) bits.push("processes ideas socially");
  if (bf.agreeableness <= 2.5) bits.push("comfortable with conflict");
  if (sjt.writtenDissent >= 4) bits.push("disagrees constructively in writing");
  if (sjt.intellectualHonesty >= 4) bits.push("acknowledges uncertainty openly");
  if (sjt.ambiguityTolerance >= 4) bits.push("operates well without playbooks");
  return bits.length ? `A candidate who is ${bits.slice(0, -1).join(", ")}${bits.length > 1 ? ", and " : ""}${bits[bits.length - 1]}.` : "Profile synthesis incomplete.";
}

// ============================================================================
// MATCHING ENGINE — THE REPLACEABLE BOUNDARY
// In v0: deterministic scoring against company criteria.
// In v1: single Claude API call with MATCHING_PROMPT, same input/output shape.
// ============================================================================

const MATCHING_PROMPT = `You are evaluating a candidate persona against a company's sanctioned artifacts for a specific role. Your output is a fit assessment — not a hiring decision.

INPUTS:
- Company artifacts: values document, role specification, team structure, sample communications
- Formal criteria with weights (derived from artifacts during template setup)
- Candidate persona: Big Five profile, SJT response signals, cross-validation flags

TASK:
1. For each criterion, estimate a 0-100 fit score based on how the persona's traits and behavioral signals would play out inside the company environment described in the artifacts.
2. Provide a one-sentence justification per criterion, referencing specific artifacts and persona signals.
3. Flag any cross-validation inconsistencies that should be probed in interview.
4. Produce an overall weighted score and a qualitative summary.

OUTPUT: Strict JSON matching the FitReport schema.

CRITICAL:
- This is a screening signal, not a decision. Frame output accordingly.
- Do not reference protected characteristics.
- Cite artifact text directly when justifying scores.
`;

function runMatchingEngine(persona, company) {
  // Deterministic mock of what the Claude call will produce.
  // Maps persona signals to each criterion with justifications.
  const { bigFive, sjtSignals } = persona;

  // Scoring functions per criterion — each blends BFI + SJT + artifact relevance
  const scores = {
    analyticalRigor: {
      score: clamp(0.6 * (sjtSignals.analyticalRigor / 5) * 100 + 0.4 * (bigFive.conscientiousness / 5) * 100),
      justification: sjtSignals.analyticalRigor >= 4
        ? `SJT responses consistently favored defensible numbers over velocity — aligns with Meridian's "homework, not speed" value.`
        : `SJT responses showed mixed prioritization between thoroughness and delivery speed. The role spec explicitly demands numbers that "hold up under IC scrutiny."`
    },
    intellectualHonesty: {
      score: clamp((sjtSignals.intellectualHonesty / 5) * 100),
      justification: sjtSignals.intellectualHonesty >= 4
        ? `Candidate showed willingness to flag uncertainty and push back on optimistic framings — matches the sample IC memo tone ("Happy to walk through the sensitivity").`
        : `Candidate defaulted toward producing confident outputs under pressure. Meridian's values document treats "I don't know yet" as a prerequisite, not a weakness.`
    },
    writtenDissent: {
      score: clamp((sjtSignals.writtenDissent / 5) * 100),
      justification: sjtSignals.writtenDissent >= 4
        ? `Candidate's SJT pattern suggests comfort formalizing disagreement — directly fits "analysts are expected to disagree with deal teams in writing."`
        : `Candidate tended toward private or deferred disagreement. The team structure ("memos circulate 48h prior, red team rotates") requires written, early dissent as a baseline behavior.`
    },
    ambiguityTolerance: {
      score: clamp(0.5 * (sjtSignals.ambiguityTolerance / 5) * 100 + 0.5 * (bigFive.openness / 5) * 100),
      justification: sjtSignals.ambiguityTolerance >= 4
        ? `Responses to the unfamiliar-sector scenario favored structured exploration over forcing output — aligns with the role spec's "comfort with ambiguity."`
        : `Candidate showed preference for clear playbooks. The team operates on model-as-argument rather than process-as-argument, which requires comfort navigating ill-defined problems.`
    },
    lowEgoCollab: {
      score: clamp(0.5 * (sjtSignals.lowEgoCollab / 5) * 100 + 0.3 * (bigFive.agreeableness / 5) * 100 + 0.2 * (5 - Math.abs(bigFive.extraversion - 3)) / 5 * 100),
      justification: sjtSignals.lowEgoCollab >= 4
        ? `Candidate navigated the VP-dismissal scenario by redirecting to evidence rather than status — matches Meridian's "no hierarchy in credit debates, the model is the argument."`
        : `Candidate's responses in conflict scenarios relied partly on hierarchy or deferral. The flat team structure expects peer-level intellectual combat regardless of title.`
    }
  };

  // Weighted overall
  const overall = Object.entries(company.criteria).reduce((sum, [key, crit]) => {
    return sum + (scores[key]?.score ?? 0) * crit.weight;
  }, 0);

  // Qualitative band
  let band, bandNote;
  if (overall >= 75) { band = "Strong fit"; bandNote = "Recommend surfacing to hiring manager for mutual opt-in."; }
  else if (overall >= 60) { band = "Plausible fit"; bandNote = "Worth a conversation; specific tensions worth probing in interview."; }
  else if (overall >= 45) { band = "Edge case"; bandNote = "Environmental fit is uncertain. Not recommended for surfacing without additional signal."; }
  else { band = "Low fit"; bandNote = "Candidate strengths likely lie in environments structurally different from Meridian's."; }

  return {
    companyId: company.id,
    companyName: company.name,
    role: company.role,
    overallScore: Math.round(overall),
    band,
    bandNote,
    criterionScores: scores,
    inconsistencyFlags: persona.inconsistencies,
    // In production: ReasoningLayer proof tree attached here
    auditTrail: {
      model: "v0-deterministic",
      timestamp: new Date().toISOString(),
      note: "v0 demo uses deterministic scoring. Production replaces this with a Claude API call wrapped in ReasoningLayer for formal proof tree generation."
    }
  };
}

function clamp(n) { return Math.max(0, Math.min(100, n)); }

// ============================================================================
// UI
// ============================================================================

const COLORS = {
  ink: "#1a1814",
  paper: "#f7f3ec",
  rule: "#d9d1c2",
  muted: "#7a7265",
  accent: "#b8391a",
  accentSoft: "#e8d4ca"
};

const FONT_DISPLAY = `'EB Garamond', 'Libre Caslon Text', 'Times New Roman', serif`;
const FONT_BODY = `'EB Garamond', Georgia, serif`;
const FONT_MONO = `'JetBrains Mono', 'Courier New', monospace`;

export default function App() {
  const [step, setStep] = useState("intro"); // intro, bfi, sjt, generating, report
  const [bfiResponses, setBfiResponses] = useState({});
  const [sjtResponses, setSjtResponses] = useState({});
  const [persona, setPersona] = useState(null);
  const [fitReport, setFitReport] = useState(null);

  const handleStart = () => setStep("bfi");

  const handleBfiSubmit = () => {
    if (Object.keys(bfiResponses).length < BFI10.length) return;
    setStep("sjt");
  };

  const handleSjtSubmit = () => {
    if (Object.keys(sjtResponses).length < SJTs.length) return;
    setStep("generating");
    // Simulate async work so the UX pattern matches the real API call
    setTimeout(() => {
      const p = synthesizePersona(bfiResponses, sjtResponses);
      setPersona(p);
      // Blind matching: persona runs against ALL seed companies; only the
      // top match is surfaced. Candidate never sees company until mutual opt-in.
      const reports = SEED_COMPANIES.map(c => runMatchingEngine(p, c));
      const best = reports.sort((a, b) => b.overallScore - a.overallScore)[0];
      setFitReport(best);
      setStep("report");
    }, 1800);
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: COLORS.paper,
      color: COLORS.ink,
      fontFamily: FONT_BODY,
      fontSize: "17px",
      lineHeight: 1.55,
      padding: "0"
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap');
        * { box-sizing: border-box; }
        .rule { border: none; border-top: 1px solid ${COLORS.rule}; margin: 0; }
        .rule-thick { border: none; border-top: 2px solid ${COLORS.ink}; margin: 0; }
        button.primary {
          background: ${COLORS.ink}; color: ${COLORS.paper};
          border: none; padding: 14px 28px;
          font-family: ${FONT_MONO}; font-size: 12px;
          letter-spacing: 0.15em; text-transform: uppercase;
          cursor: pointer; transition: background 0.2s;
        }
        button.primary:hover:not(:disabled) { background: ${COLORS.accent}; }
        button.primary:disabled { background: ${COLORS.muted}; cursor: not-allowed; }
        button.choice {
          width: 100%; text-align: left;
          background: transparent; color: ${COLORS.ink};
          border: 1px solid ${COLORS.rule};
          padding: 16px 20px; margin-bottom: 10px;
          font-family: ${FONT_BODY}; font-size: 16px; line-height: 1.5;
          cursor: pointer; transition: all 0.15s;
        }
        button.choice:hover { border-color: ${COLORS.ink}; background: #fff; }
        button.choice.selected {
          border-color: ${COLORS.ink}; background: ${COLORS.ink}; color: ${COLORS.paper};
        }
        .likert { display: flex; gap: 6px; }
        .likert button {
          flex: 1; padding: 10px 0;
          background: transparent; border: 1px solid ${COLORS.rule};
          font-family: ${FONT_MONO}; font-size: 13px;
          cursor: pointer; transition: all 0.15s;
          color: ${COLORS.ink};
        }
        .likert button:hover { border-color: ${COLORS.ink}; }
        .likert button.selected {
          background: ${COLORS.ink}; color: ${COLORS.paper}; border-color: ${COLORS.ink};
        }
        .label-mono {
          font-family: ${FONT_MONO}; font-size: 11px;
          letter-spacing: 0.18em; text-transform: uppercase;
          color: ${COLORS.muted};
        }
        .drop-cap::first-letter {
          font-size: 3.2em; float: left; line-height: 0.9;
          padding: 4px 8px 0 0; font-weight: 500;
        }
        @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
        .pulse-dot {
          display: inline-block; width: 8px; height: 8px;
          background: ${COLORS.accent}; border-radius: 50%;
          animation: pulse 1.4s ease-in-out infinite;
        }
        .pulse-dot:nth-child(2) { animation-delay: 0.2s; }
        .pulse-dot:nth-child(3) { animation-delay: 0.4s; }
      `}</style>

      {/* Masthead */}
      <header style={{
        borderBottom: `2px solid ${COLORS.ink}`,
        padding: "28px 48px 20px",
        display: "flex", justifyContent: "space-between", alignItems: "flex-end"
      }}>
        <div>
          <div className="label-mono">Screening Instrument · v0</div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: "32px", fontWeight: 500, marginTop: 4, letterSpacing: "-0.01em" }}>
            Parallax<span style={{ color: COLORS.accent }}>.</span>
          </div>
        </div>
        <div className="label-mono" style={{ textAlign: "right" }}>
          <div>Environmental Fit Assessment</div>
          <div style={{ marginTop: 4 }}>Not a Hiring Decision Tool</div>
        </div>
      </header>

      <main style={{ maxWidth: 860, margin: "0 auto", padding: "48px 32px 80px" }}>
        {step === "intro" && <IntroScreen onStart={handleStart} />}
        {step === "bfi" && (
          <BfiScreen
            responses={bfiResponses}
            setResponses={setBfiResponses}
            onSubmit={handleBfiSubmit}
          />
        )}
        {step === "sjt" && (
          <SjtScreen
            responses={sjtResponses}
            setResponses={setSjtResponses}
            onSubmit={handleSjtSubmit}
          />
        )}
        {step === "generating" && <GeneratingScreen />}
        {step === "report" && persona && fitReport && (
          <ReportScreen persona={persona} fitReport={fitReport} companies={SEED_COMPANIES} />
        )}
      </main>

      <footer style={{
        borderTop: `1px solid ${COLORS.rule}`,
        padding: "24px 48px",
        color: COLORS.muted, fontSize: 13,
        display: "flex", justifyContent: "space-between"
      }}>
        <div className="label-mono">Screening signal · Not a decision</div>
        <div className="label-mono">Blind matching · Mutual opt-in required</div>
      </footer>
    </div>
  );
}

function IntroScreen({ onStart }) {
  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 16 }}>Candidate Intake</div>
      <h1 style={{
        fontFamily: FONT_DISPLAY, fontSize: 56, fontWeight: 500,
        lineHeight: 1.1, letterSpacing: "-0.02em", margin: "0 0 32px"
      }}>
        Before you try to impress anyone, tell us who you actually are.
      </h1>
      <p className="drop-cap" style={{ fontSize: 19, lineHeight: 1.65, marginBottom: 20 }}>
        You will not be told which companies you're being considered for. This is deliberate.
        When candidates know the target, they tailor. When they tailor, the signal degrades.
        We evaluate how you'd behave inside a company's actual environment — not how you present
        yourself against a job description.
      </p>
      <p style={{ fontSize: 17, marginBottom: 20, color: COLORS.muted }}>
        The assessment takes about twelve minutes. You'll answer ten short personality items
        and three situational judgment scenarios. We synthesize a behavioral persona and run it
        against the company environments in our template library. If there's a match, both you
        and the hiring manager are notified. Either party can decline without explanation.
      </p>
      <hr className="rule" style={{ margin: "40px 0" }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 32, marginBottom: 48 }}>
        <Pillar n="I" title="Environmental fit" body="Simulation against specific company artifacts, not generic trait norms." />
        <Pillar n="II" title="Blind to both sides" body="You don't know which companies. They don't see your profile until match." />
        <Pillar n="III" title="Auditable" body="Every score decomposes to the artifact text and persona signal that produced it." />
      </div>
      <button className="primary" onClick={onStart}>Begin intake →</button>
    </div>
  );
}

function Pillar({ n, title, body }) {
  return (
    <div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 32, color: COLORS.accent, fontStyle: "italic" }}>{n}</div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500, margin: "4px 0 8px" }}>{title}</div>
      <div style={{ fontSize: 15, color: COLORS.muted, lineHeight: 1.5 }}>{body}</div>
    </div>
  );
}

function BfiScreen({ responses, setResponses, onSubmit }) {
  const complete = Object.keys(responses).length;
  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 12 }}>Section I of II · Big Five Inventory (BFI-10)</div>
      <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 34, fontWeight: 500, letterSpacing: "-0.01em", margin: "0 0 12px" }}>
        Ten items. Answer honestly — not strategically.
      </h2>
      <p style={{ color: COLORS.muted, marginBottom: 32, fontSize: 16 }}>
        Rate each statement from 1 (strongly disagree) to 5 (strongly agree). The validated
        BFI-10 is deliberately short; social-desirability bias is managed by cross-validation
        in Section II rather than by lengthening this section.
      </p>
      {BFI10.map((item, idx) => (
        <div key={item.id} style={{ padding: "20px 0", borderBottom: `1px solid ${COLORS.rule}` }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 12 }}>
            <div className="label-mono" style={{ minWidth: 28 }}>{String(idx + 1).padStart(2, "0")}</div>
            <div style={{ fontSize: 17, flex: 1 }}>{item.text}</div>
          </div>
          <div className="likert" style={{ marginLeft: 44 }}>
            {[1, 2, 3, 4, 5].map(v => (
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
        <div className="label-mono">{complete} of {BFI10.length} answered</div>
        <button className="primary" disabled={complete < BFI10.length} onClick={onSubmit}>
          Continue to scenarios →
        </button>
      </div>
    </div>
  );
}

function SjtScreen({ responses, setResponses, onSubmit }) {
  const complete = Object.keys(responses).length;
  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 12 }}>Section II of II · Situational Judgment</div>
      <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 34, fontWeight: 500, letterSpacing: "-0.01em", margin: "0 0 12px" }}>
        Three scenarios. Pick the option closest to what you would actually do.
      </h2>
      <p style={{ color: COLORS.muted, marginBottom: 40, fontSize: 16 }}>
        Not what you think sounds best. These scenarios are drawn from the daily texture of
        analyst work in environments where models are treated as arguments and disagreement is
        part of the job.
      </p>
      {SJTs.map((sjt, idx) => (
        <div key={sjt.id} style={{ marginBottom: 48, paddingBottom: 32, borderBottom: `1px solid ${COLORS.rule}` }}>
          <div className="label-mono" style={{ marginBottom: 12 }}>Scenario {idx + 1}</div>
          <p style={{ fontSize: 18, lineHeight: 1.6, fontStyle: "italic", color: COLORS.ink, marginBottom: 20, borderLeft: `3px solid ${COLORS.accent}`, paddingLeft: 20 }}>
            {sjt.scenario}
          </p>
          <p style={{ fontSize: 17, fontWeight: 500, marginBottom: 16 }}>{sjt.question}</p>
          {sjt.options.map(opt => (
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
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="label-mono">{complete} of {SJTs.length} answered</div>
        <button className="primary" disabled={complete < SJTs.length} onClick={onSubmit}>
          Synthesize persona →
        </button>
      </div>
    </div>
  );
}

function GeneratingScreen() {
  return (
    <div style={{ padding: "120px 0", textAlign: "center" }}>
      <div className="label-mono" style={{ marginBottom: 24 }}>
        <span className="pulse-dot"></span>&nbsp;
        <span className="pulse-dot"></span>&nbsp;
        <span className="pulse-dot"></span>
      </div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 28, fontStyle: "italic", color: COLORS.muted }}>
        Synthesizing persona and running simulation…
      </div>
      <div style={{ marginTop: 20, fontSize: 15, color: COLORS.muted, maxWidth: 500, margin: "20px auto 0" }}>
        Mapping BFI signals to behavioral dimensions. Cross-validating against SJT responses.
        Running persona against {SEED_COMPANIES.length} company environment{SEED_COMPANIES.length > 1 ? "s" : ""}.
      </div>
    </div>
  );
}

function ReportScreen({ persona, fitReport, companies }) {
  const company = companies.find(c => c.id === fitReport.companyId);
  const { bigFive, sjtSignals, inconsistencies } = persona;

  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 12 }}>Fit Report · Confidential · Screening Signal</div>
      <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 44, fontWeight: 500, letterSpacing: "-0.015em", margin: "0 0 8px", lineHeight: 1.1 }}>
        {fitReport.band}.
      </h2>
      <p style={{ fontSize: 18, color: COLORS.muted, marginBottom: 8, fontStyle: "italic" }}>
        {fitReport.bandNote}
      </p>
      <hr className="rule-thick" style={{ margin: "32px 0 24px" }} />

      {/* Headline score + company */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 40, marginBottom: 40 }}>
        <div>
          <div className="label-mono" style={{ marginBottom: 8 }}>Matched environment</div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 500 }}>{fitReport.companyName}</div>
          <div style={{ color: COLORS.muted, fontSize: 16 }}>{fitReport.role}</div>
          <div style={{ color: COLORS.muted, fontSize: 14, marginTop: 8, fontStyle: "italic" }}>{company?.tagline}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="label-mono" style={{ marginBottom: 8 }}>Weighted fit</div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 72, fontWeight: 500, lineHeight: 1, color: COLORS.accent, letterSpacing: "-0.03em" }}>
            {fitReport.overallScore}
          </div>
          <div className="label-mono">of 100</div>
        </div>
      </div>

      {/* Persona narrative */}
      <div style={{ background: "#fff", border: `1px solid ${COLORS.rule}`, padding: "24px 28px", marginBottom: 40 }}>
        <div className="label-mono" style={{ marginBottom: 10 }}>Persona summary</div>
        <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontStyle: "italic", lineHeight: 1.5 }}>
          {persona.narrative}
        </div>
      </div>

      {/* Criterion breakdown */}
      <div className="label-mono" style={{ marginBottom: 16 }}>Scoring decomposition</div>
      {Object.entries(fitReport.criterionScores).map(([key, val]) => {
        const crit = company.criteria[key];
        return (
          <div key={key} style={{ padding: "20px 0", borderBottom: `1px solid ${COLORS.rule}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
              <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500 }}>
                {formatCriterion(key)}
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                <span className="label-mono">weight {Math.round(crit.weight * 100)}%</span>
                <span style={{ fontFamily: FONT_MONO, fontSize: 20, fontWeight: 500, minWidth: 48, textAlign: "right" }}>
                  {Math.round(val.score)}
                </span>
              </div>
            </div>
            {/* Bar */}
            <div style={{ height: 3, background: COLORS.rule, marginBottom: 12, position: "relative" }}>
              <div style={{
                position: "absolute", top: 0, left: 0, height: "100%",
                width: `${val.score}%`,
                background: val.score >= 70 ? COLORS.ink : val.score >= 50 ? COLORS.accent : COLORS.muted
              }} />
            </div>
            <div style={{ fontSize: 15, color: COLORS.muted, lineHeight: 1.55 }}>
              {val.justification}
            </div>
          </div>
        );
      })}

      {/* Inconsistency flags */}
      {inconsistencies.length > 0 && (
        <div style={{ marginTop: 40, background: COLORS.accentSoft, padding: "24px 28px", borderLeft: `3px solid ${COLORS.accent}` }}>
          <div className="label-mono" style={{ marginBottom: 10, color: COLORS.accent }}>Cross-validation flags</div>
          <div style={{ fontSize: 14, color: COLORS.muted, marginBottom: 16 }}>
            Signals that don't cleanly align between self-report and situational response.
            Neither good nor bad on their own — useful questions for a human interviewer.
          </div>
          {inconsistencies.map((flag, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: COLORS.accent, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
                {flag.type}
              </div>
              <div style={{ fontSize: 15, lineHeight: 1.55 }}>{flag.note}</div>
            </div>
          ))}
        </div>
      )}

      {/* Big Five panel */}
      <div style={{ marginTop: 40 }}>
        <div className="label-mono" style={{ marginBottom: 16 }}>Underlying persona signals</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32 }}>
          <div>
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 16, fontWeight: 500, marginBottom: 10 }}>Big Five (BFI-10)</div>
            {Object.entries(bigFive).map(([k, v]) => (
              <MiniBar key={k} label={k} value={v} max={5} />
            ))}
          </div>
          <div>
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 16, fontWeight: 500, marginBottom: 10 }}>SJT behavioral signals</div>
            {Object.entries(sjtSignals).map(([k, v]) => (
              <MiniBar key={k} label={formatCriterion(k)} value={v} max={5} />
            ))}
          </div>
        </div>
      </div>

      {/* Audit trail */}
      <div style={{ marginTop: 48, paddingTop: 24, borderTop: `1px solid ${COLORS.rule}`, fontSize: 13, color: COLORS.muted, fontFamily: FONT_MONO }}>
        <div>audit · model={fitReport.auditTrail.model} · ts={fitReport.auditTrail.timestamp}</div>
        <div style={{ marginTop: 6, fontStyle: "italic" }}>{fitReport.auditTrail.note}</div>
      </div>

      {/* Mutual opt-in CTA */}
      <div style={{ marginTop: 40, textAlign: "center", padding: "32px 0", borderTop: `2px solid ${COLORS.ink}` }}>
        <div style={{ fontFamily: FONT_DISPLAY, fontSize: 22, fontStyle: "italic", marginBottom: 20 }}>
          If this looks right to you, the hiring manager will be notified.<br />
          An interview happens only if both of you opt in.
        </div>
        <button className="primary" style={{ marginRight: 12 }}>Request introduction</button>
        <button className="primary" style={{ background: "transparent", color: COLORS.ink, border: `1px solid ${COLORS.ink}` }}>
          Not this one, thanks
        </button>
      </div>
    </div>
  );
}

function MiniBar({ label, value, max }) {
  const pct = (value / max) * 100;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, marginBottom: 4 }}>
        <span style={{ textTransform: "capitalize" }}>{label}</span>
        <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: COLORS.muted }}>{value.toFixed(1)}</span>
      </div>
      <div style={{ height: 2, background: COLORS.rule }}>
        <div style={{ height: "100%", width: `${pct}%`, background: COLORS.ink }} />
      </div>
    </div>
  );
}

function formatCriterion(k) {
  return k
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, s => s.toUpperCase())
    .trim();
}
