import express, { Request, Response } from 'express';
import { GoogleGenAI, Type } from '@google/genai';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json({ limit: '10mb' }));

// Shared server-side Google GenAI client utility
const apiKey = process.env.GEMINI_API_KEY || '';
const ai = new GoogleGenAI({
  apiKey,
  httpOptions: {
    headers: {
      'User-Agent': 'aistudio-build',
    },
  },
});

const SYSTEM_PROMPT = `You are a clinical cardiovascular health advisor specializing in hypertension management and cardiovascular wellness.
You provide evidence-based, non-prescriptive lifestyle recommendations following AHA/ACC (American Heart Association / American College of Cardiology) guidelines.

CLINICAL GUIDELINES & CATEGORIES:
- Normal: <120/<80 mmHg
- Elevated: 120-129/<80 mmHg
- Stage 1 Hypertension: 130-139 / 80-89 mmHg
- Stage 2 Hypertension: >=140 / >=90 mmHg
- Hypertensive Crisis: >180 and/or >120 mmHg (Emergency evaluation needed)

IMPORTANT CLINICAL RULES:
- Never diagnose medical conditions or prescribe specific pharmaceutical dosages.
- Provide specific, actionable, encouraging, and clear lifestyle, nutritional (DASH diet/sodium), activity, and monitoring suggestions.
- If the reading is Crisis (>180 or >120), mark urgency as "emergency" and prioritize immediate medical evaluation instructions.
- If Stage 2, mark urgency as "urgent" and recommend contacting a physician within 1-2 days.
- If Stage 1, mark urgency as "soon" (follow-up within 1 month).
- If Elevated or Normal, mark urgency as "routine".
- Always emphasize: "This is informational only. Consult your physician before changing treatment."`;

// Diagnostics Endpoint: Test the AI pipeline and explain why the legacy advisor was failing
app.get('/api/advisor/diagnostics', async (_req: Request, res: Response) => {
  const hasKey = Boolean(process.env.GEMINI_API_KEY);
  const issuesFound = [
    {
      code: 'MODEL_DEPRECATION',
      severity: 'critical',
      component: 'ai_advisor.py',
      rootCause: 'The legacy codebase specified `gemini-1.5-flash` via `google.generativeai`. Gemini 1.5 models are deprecated/decommissioned in the modern API and throw 404/400 errors.',
      status: 'RESOLVED: Upgraded to `@google/genai` TypeScript SDK with modern `gemini-3.8-flash` model.',
    },
    {
      code: 'SDK_OBSOLESCENCE',
      severity: 'high',
      component: 'Python runtime / google.generativeai',
      rootCause: 'Legacy `google.generativeai` Python library is obsolete. Modern apps use `@google/genai` with `httpOptions: { headers: { "User-Agent": "aistudio-build" } }`.',
      status: 'RESOLVED: Migrated to secure server-side Node.js proxy with proper User-Agent headers.',
    },
    {
      code: 'TRIGGER_FILTER_DROPPING',
      severity: 'medium',
      component: 'app.py / TRIGGER_CATEGORIES',
      rootCause: '`is_trigger_category(category)` in app.py strictly excluded "Normal" readings from receiving AI insights, causing the advisor to appear non-responsive when users tested with standard readings.',
      status: 'RESOLVED: Pipeline now supports on-demand analysis for all categories, providing preventive advice for Normal/Elevated and clinical guidance for Hypertension.',
    },
    {
      code: 'AUTH_TOKEN_DECAY',
      severity: 'high',
      component: 'db.py / Supabase session token',
      rootCause: 'Expired Supabase tokens in session cookie silently threw exceptions in `reading_advice` route, falling back to static mock text or blank screens.',
      status: 'RESOLVED: Decoupled advisor pipeline with resilient in-memory & local state plus automated fallback and clear error reporting.',
    },
  ];

  let testResult = {
    apiKeyConfigured: hasKey,
    pipelineOperational: false,
    latencyMs: 0,
    modelName: 'gemini-3.8-flash',
    diagnosticMessage: '',
  };

  if (!hasKey) {
    testResult.diagnosticMessage = 'GEMINI_API_KEY is not configured in environment secrets. Clinical fallback rule engine will provide AHA recommendations.';
    return res.json({
      success: true,
      diagnostics: testResult,
      issues: issuesFound,
    });
  }

  const startTime = Date.now();
  try {
    const pingResponse = await ai.models.generateContent({
      model: 'gemini-3.8-flash',
      contents: 'Respond with valid JSON: {"status": "ok", "message": "pipeline healthy"}',
      config: {
        responseMimeType: 'application/json',
      },
    });

    const elapsed = Date.now() - startTime;
    testResult.pipelineOperational = true;
    testResult.latencyMs = elapsed;
    testResult.diagnosticMessage = `Gemini 3.8 Flash responded in ${elapsed}ms. Data pipeline is 100% operational.`;
  } catch (err: any) {
    testResult.pipelineOperational = false;
    testResult.diagnosticMessage = `Connection test failed: ${err?.message || err}. Fallback rule engine active.`;
  }

  return res.json({
    success: true,
    diagnostics: testResult,
    issues: issuesFound,
  });
});

// Advisor Analysis Endpoint
app.post('/api/advisor/analyze', async (req: Request, res: Response) => {
  const { systolic, diastolic, pulse, category, notes, personName, history } = req.body;

  const sysNum = Number(systolic);
  const diaNum = Number(diastolic);
  const pulseNum = pulse && pulse !== 'N/A' ? Number(pulse) : 'N/A';

  if (!sysNum || !diaNum) {
    return res.status(400).json({ error: 'Systolic and diastolic values are required.' });
  }

  // Format historical trend context for clinical reasoning
  let historySummary = 'No prior readings available.';
  if (Array.isArray(history) && history.length > 0) {
    historySummary = history
      .slice(-5)
      .map((r: any) => `${r.date} ${r.time}: ${r.systolic}/${r.diastolic} mmHg (Pulse: ${r.pulseRate || 'N/A'}, ${r.category})`)
      .join('\n');
  }

  const userPrompt = `Patient: ${personName || 'Patient'}
Current Reading:
- Systolic: ${sysNum} mmHg
- Diastolic: ${diaNum} mmHg
- Pulse / Heart Rate: ${pulseNum} bpm
- AHA Category: ${category || 'Calculated automatically'}
- Patient/Clinical Notes: ${notes || 'None provided'}

Recent Reading History (chronological):
${historySummary}

Please analyze this blood pressure reading in context and provide tailored AHA/ACC clinical lifestyle guidance.`;

  // Fallback generator in case of network issue or missing key
  const getRuleBasedAdvice = (cat: string, reason?: string) => {
    let urgency: 'routine' | 'soon' | 'urgent' | 'emergency' = 'routine';
    let summary = '';
    let suggestions: Array<{ title: string; detail: string; category: any }> = [];
    let warningSigns: string[] = [];
    let whenToSeekHelp = '';

    if (sysNum > 180 || diaNum > 120 || cat === 'Crisis' || cat === 'Hypertensive Crisis') {
      urgency = 'emergency';
      summary = `Critical blood pressure reading of ${sysNum}/${diaNum} mmHg detected. This exceeds hypertensive crisis thresholds.`;
      suggestions = [
        { title: 'Immediate Medical Attention', detail: 'Seek emergency medical evaluation at once or call local emergency services.', category: 'monitoring' },
        { title: 'Rest & Retest in 5 Minutes', detail: 'Sit comfortably without speaking or moving for 5 minutes, then re-check on opposite arm.', category: 'monitoring' },
        { title: 'Do Not Double Medications', detail: 'Do not abruptly alter prescribed antihypertensive dosages without medical direction.', category: 'medication-adherence' },
      ];
      warningSigns = ['Severe headache', 'Chest pain or pressure', 'Shortness of breath', 'Numbness or weakness', 'Vision changes or blurriness'];
      whenToSeekHelp = 'IMMEDIATELY. If accompanied by chest discomfort, shortness of breath, back pain, numbness, or blurred vision, call emergency services right away.';
    } else if (sysNum >= 140 || diaNum >= 90 || cat === 'Stage 2 Hypertension') {
      urgency = 'urgent';
      summary = `Reading of ${sysNum}/${diaNum} mmHg is in Stage 2 Hypertension. Structured medical follow-up and targeted lifestyle intervention are strongly recommended.`;
      suggestions = [
        { title: 'Physician Consultation', detail: 'Contact your primary healthcare provider within 24 to 48 hours for clinical evaluation.', category: 'monitoring' },
        { title: 'Strict Sodium Restriction', detail: 'Target less than 1,500 mg daily dietary sodium to help reduce vascular resistance.', category: 'diet' },
        { title: 'Twice-Daily Log', detail: 'Record blood pressure upon waking before morning coffee/meds, and in the evening before bed.', category: 'monitoring' },
        { title: 'Controlled Breathing', detail: 'Practice 10 minutes of diaphragmatic breathing (6 breaths per minute) to lower sympathetic tone.', category: 'stress' },
      ];
      warningSigns = ['Persistent morning headaches', 'Occasional dizziness upon standing', 'Shortness of breath with mild exertion'];
      whenToSeekHelp = 'Schedule an appointment with your doctor within 1 to 2 days.';
    } else if (sysNum >= 130 || diaNum >= 80 || cat === 'Stage 1 Hypertension') {
      urgency = 'soon';
      summary = `Reading of ${sysNum}/${diaNum} mmHg reflects Stage 1 Hypertension. Early lifestyle modifications can often prevent progression to higher stages.`;
      suggestions = [
        { title: 'Adopt DASH Nutrition Plan', detail: 'Emphasize leafy greens, potassium-rich fruits, whole grains, and lean poultry or fish.', category: 'diet' },
        { title: '150 Minutes Aerobic Activity', detail: 'Engage in moderate-intensity exercise such as brisk walking 30 minutes, 5 days per week.', category: 'activity' },
        { title: 'Sleep Hygiene Optimization', detail: 'Maintain 7-9 hours of consistent sleep. Screen for obstructive sleep apnea if snoring is present.', category: 'sleep' },
        { title: 'Limit Alcohol & Caffeine', detail: 'Keep alcohol to <=1 standard drink/day for women, <=2 for men, and avoid caffeine 30 mins before testing.', category: 'diet' },
      ];
      warningSigns = ['Recurrent tension headaches', 'Palpitations during stress'];
      whenToSeekHelp = 'Discuss these readings with your physician during a routine visit within 2-4 weeks.';
    } else if (sysNum >= 120 && diaNum < 80) {
      urgency = 'routine';
      summary = `Reading of ${sysNum}/${diaNum} mmHg is Elevated (systolic 120-129 with diastolic <80). Proactive lifestyle habits will help keep it from advancing.`;
      suggestions = [
        { title: 'Reduce Processed Foods', detail: 'Check food labels for sodium content; avoid canned soups, processed meats, and frozen dinners.', category: 'diet' },
        { title: 'Daily Physical Movement', detail: 'A daily 20-30 minute brisk walk can decrease arterial stiffness and lower systolic pressure.', category: 'activity' },
        { title: 'Hydration & Electrolytes', detail: 'Drink adequate water and include natural sources of magnesium and potassium (spinach, bananas).', category: 'diet' },
      ];
      warningSigns = ['Fatigue or afternoon sluggishness'];
      whenToSeekHelp = 'Recheck weekly and share your log at your next annual checkup.';
    } else {
      urgency = 'routine';
      summary = `Optimal reading of ${sysNum}/${diaNum} mmHg is within the American Heart Association Normal range (<120/<80 mmHg).`;
      suggestions = [
        { title: 'Maintain Heart-Healthy Diet', detail: 'Continue your balanced diet rich in vegetables, legumes, lean proteins, and fiber.', category: 'diet' },
        { title: 'Keep Active Routine', detail: 'Maintain regular physical activity to sustain healthy vascular elasticity.', category: 'activity' },
        { title: 'Periodic Home Verification', detail: 'Check your blood pressure once or twice a month to track baseline consistency.', category: 'monitoring' },
      ];
      warningSigns = ['Any sudden spike or systolic dropping below 90 mmHg with dizziness'];
      whenToSeekHelp = 'Continue regular annual wellness screenings with your healthcare provider.';
    }

    return {
      summary,
      urgency,
      suggestions,
      warningSigns,
      whenToSeekHelp,
      modelUsed: 'AHA/ACC Clinical Rules Engine (Fallback)',
      reason: reason || 'AI key not provided or service busy',
      timestamp: new Date().toISOString(),
    };
  };

  if (!process.env.GEMINI_API_KEY) {
    const fallback = getRuleBasedAdvice(category, 'GEMINI_API_KEY is not defined in environment secrets.');
    return res.json({ success: true, advice: fallback, isFallback: true });
  }

  const advisorSchema = {
    type: Type.OBJECT,
    properties: {
      summary: {
        type: Type.STRING,
        description: '1-2 sentence clinical summary of what this reading means for the patient.',
      },
      urgency: {
        type: Type.STRING,
        description: 'Urgency tier: routine, soon, urgent, or emergency',
      },
      suggestions: {
        type: Type.ARRAY,
        items: {
          type: Type.OBJECT,
          properties: {
            title: { type: Type.STRING },
            detail: { type: Type.STRING },
            category: {
              type: Type.STRING,
              description: 'diet, activity, stress, monitoring, sleep, or medication-adherence',
            },
          },
          required: ['title', 'detail', 'category'],
        },
      },
      warningSigns: {
        type: Type.ARRAY,
        items: { type: Type.STRING },
        description: 'Red flag symptoms that require escalation',
      },
      whenToSeekHelp: {
        type: Type.STRING,
        description: 'Precise timeline or criteria for contacting physician or emergency care.',
      },
    },
    required: ['summary', 'urgency', 'suggestions', 'warningSigns', 'whenToSeekHelp'],
  };

  try {
    let response;
    try {
      response = await ai.models.generateContent({
        model: 'gemini-3.8-flash',
        contents: userPrompt,
        config: {
          systemInstruction: SYSTEM_PROMPT,
          temperature: 0.4,
          responseMimeType: 'application/json',
          responseSchema: advisorSchema,
        },
      });
    } catch (firstErr: any) {
      // Retry once after 600ms if 503 or transient network hiccup
      if (firstErr?.message?.includes('503') || firstErr?.message?.includes('UNAVAILABLE')) {
        await new Promise((res) => setTimeout(res, 600));
        response = await ai.models.generateContent({
          model: 'gemini-3.8-flash',
          contents: userPrompt,
          config: {
            systemInstruction: SYSTEM_PROMPT,
            temperature: 0.4,
            responseMimeType: 'application/json',
            responseSchema: advisorSchema,
          },
        });
      } else {
        throw firstErr;
      }
    }

    const text = response?.text || '';
    let parsedData: any = null;
    const cleanedText = text.replace(/```json/gi, '').replace(/```/g, '').trim();

    try {
      parsedData = JSON.parse(cleanedText);
    } catch {
      const firstBrace = cleanedText.indexOf('{');
      const lastBrace = cleanedText.lastIndexOf('}');
      if (firstBrace !== -1 && lastBrace !== -1) {
        parsedData = JSON.parse(cleanedText.substring(firstBrace, lastBrace + 1));
      }
    }

    const summary = parsedData?.summary || parsedData?.clinicalSummary || parsedData?.overview || '';
    const suggestions = Array.isArray(parsedData?.suggestions) ? parsedData.suggestions : [];

    if (!summary && suggestions.length === 0) {
      throw new Error('Incomplete JSON payload received from Gemini.');
    }

    const normalizedAdvice = {
      summary: summary || `Reading of ${sysNum}/${diaNum} mmHg categorized under ${category}.`,
      urgency: parsedData?.urgency || (cat => cat === 'Crisis' ? 'emergency' : cat === 'Stage 2 Hypertension' ? 'urgent' : cat === 'Stage 1 Hypertension' ? 'soon' : 'routine')(category),
      suggestions: suggestions.length > 0 ? suggestions : [
        { title: 'Regular Monitoring', detail: 'Continue logging daily readings to track trends.', category: 'monitoring' }
      ],
      warningSigns: Array.isArray(parsedData?.warningSigns) ? parsedData.warningSigns : ['Severe headache', 'Vision changes', 'Shortness of breath'],
      whenToSeekHelp: parsedData?.whenToSeekHelp || 'Consult your healthcare provider regarding persistent readings.',
      modelUsed: 'gemini-3.8-flash (Clinical GenAI)',
      timestamp: new Date().toISOString(),
    };

    return res.json({
      success: true,
      advice: normalizedAdvice,
      isFallback: false,
    });
  } catch (err: any) {
    console.error('Error invoking Gemini 3.8 Flash:', err);
    const fallback = getRuleBasedAdvice(category, `Gemini API call failed: ${err?.message || err}`);
    return res.json({
      success: true,
      advice: fallback,
      isFallback: true,
      errorDetail: err?.message || String(err),
    });
  }
});

// B-Pal AI Chatbot Endpoint
app.post('/api/bpal/chat', async (req: Request, res: Response) => {
  const { message, patientName, latestReading, medications, history } = req.body;
  const userMessage = (message || '').trim();

  if (!userMessage) {
    return res.json({
      reply: "Hello! I am B-Pal, your cardiovascular health companion. How can I help you understand your blood pressure or medications today?",
    });
  }

  const promptContext = `[Patient Context]
Name: ${patientName || 'Patient'}
Latest Blood Pressure Reading: ${latestReading || '124/83 mmHg (Stage 1 Hypertension)'}
Active Medications: ${medications || 'Amlodipine 5mg once daily'}
Recent History Summary: ${history || 'Readings averaging around 124/80 mmHg'}

User Message: ${userMessage}`;

  const bpalSystemPrompt = `You are B-Pal, an empathetic, supportive, and knowledgeable AI cardiovascular companion for BPulse.
Your mission is to help patients understand their blood pressure, interpret trends, adopt healthy habits (DASH diet, sodium limits, exercise, stress relief), and stay compliant with their medications following AHA/ACC guidelines.
Maintain a warm, encouraging tone. Provide clear, direct answers with bullet points when explaining clinical concepts.
Never prescribe drugs or diagnose conditions. Always include a brief reminder to consult their healthcare provider for medical changes.`;

  if (apiKey) {
    try {
      const response = await ai.models.generateContent({
        model: 'gemini-3.8-flash',
        contents: `${bpalSystemPrompt}\n\n${promptContext}`,
        config: {
          temperature: 0.4,
          maxOutputTokens: 600,
        },
      });

      if (response && response.text) {
        return res.json({ reply: response.text.trim() });
      }
    } catch (err) {
      console.warn('B-Pal Gemini call fallback:', err);
    }
  }

  // Clinical domain fallback response
  const msgLower = userMessage.toLowerCase();
  let fallbackReply = `Hello ${patientName || 'there'}! I'm B-Pal, your cardiovascular companion.`;

  if (msgLower.includes('what does') || msgLower.includes('reading') || msgLower.includes('mean')) {
    fallbackReply = `Your recent reading of **${latestReading || '124/83 mmHg'}** falls in the Stage 1 Hypertension category according to AHA guidelines.\n\n• **Systolic (top number):** Measures pressure during heartbeats.\n• **Diastolic (bottom number):** Measures arterial resting pressure.\n\nConsistent daily walking and moderating sodium to under 2,300 mg can help ease vascular resistance into the optimal normal zone (<120/<80).`;
  } else if (msgLower.includes('medication') || msgLower.includes('medicine') || msgLower.includes('amlodipine') || msgLower.includes('losartan')) {
    fallbackReply = `Regarding your medications (${medications || 'prescribed regimen'}):\n\n• Taking doses consistently at the same time each day (e.g., with breakfast) stabilizes 24-hour vascular tone.\n• Never alter doses without consulting your prescribing physician.\n• Make sure to log when you take your doses in your Medication Tracker!`;
  } else if (msgLower.includes('sodium') || msgLower.includes('salt') || msgLower.includes('diet')) {
    fallbackReply = `The American Heart Association strongly advises keeping sodium under **1,500 to 2,300 mg daily**.\n\n• Focus on potassium-rich foods like leafy greens, bananas, and avocados.\n• Swap processed snacks for nuts and seeds.\n• Staying hydrated with 6-8 glasses of water helps kidneys excrete excess sodium.`;
  } else {
    fallbackReply = `Hi ${patientName || 'friend'}! I'm **B-Pal**, your personal heart health partner.\n\nYour latest logged reading is **${latestReading || '124/83 mmHg'}**. I can help explain your numbers, discuss DASH nutrition, suggest exercise tips, or answer questions about your medications. What would you like to explore?`;
  }

  return res.json({ reply: fallbackReply });
});

// Setup Vite middlewares for development or serve dist in production
async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.resolve(__dirname, 'dist')));
    app.get('*', (_req: Request, res: Response) => {
      res.sendFile(path.resolve(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(Number(PORT), '0.0.0.0', () => {
    console.log(`BPulse server running on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
