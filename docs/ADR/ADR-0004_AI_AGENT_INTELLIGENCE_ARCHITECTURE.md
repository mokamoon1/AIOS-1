أنشئ وثيقة ADR-0004_AI_AGENT_INTELLIGENCE_ARCHITECTURE.md

اتبع نفس أسلوب وتنسيق وثائق AIOS الحالية.

قبل الكتابة:
- اقرأ AIOS-002_PROJECT_CONSTITUTION.md
- اقرأ AIOS-101_SYSTEM_ARCHITECTURE.md
- اقرأ AIOS-102_AGENT_ARCHITECTURE.md
- اقرأ AIOS-403_AGENT_DESIGN.md
- اقرأ AIOS-405_ANALYSIS_ENGINE_DESIGN.md
- اقرأ AIOS-406_DECISION_ENGINE_DESIGN.md
- اقرأ AIOS-1108_AI_DEVELOPMENT_GUIDELINES.md

هدف ADR:
حسم طريقة عمل الذكاء داخل AIOS ومنع أي غموض بين Agents و Engines و Decision Engine.

يجب أن يحتوي القرار على:

# 1. المشكلة الحالية
شرح التعارض:
- هل الوكلاء تعتمد على LLM؟
- هل الوكلاء قواعد برمجية؟
- من يملك القرار النهائي؟

# 2. القرار المعتمد

اعتماد نموذج Hybrid Architecture:

## Engines
مسؤولة عن:
- الحسابات
- التحليل
- التقييم
- إنتاج Scores
- إنتاج بيانات قابلة للاختبار

أمثلة:
- Market Engine
- Fundamental Engine
- Technical Engine
- Risk Engine
- Portfolio Engine
- Decision Engine

## Agents
مسؤولة عن:
- التنسيق
- إدارة السياق
- تفسير النتائج
- التواصل بين المكونات
- إنتاج تقارير مفهومة

ولا تستطيع:
- تجاوز القواعد
- تغيير نتائج المحركات
- تجاوز Shariah Gate
- تجاوز Risk Controls

# 3. دور LLM

وضح أن:

LLM يستخدم في:
- Explanation
- Summarization
- Natural Language Interface

ولا يستخدم في:
- الحسابات المالية
- تحديد BUY/SELL مباشرة
- تعديل القواعد
- تجاوز Decision Engine

# 4. Decision Authority

اعتمد:

Analysis Engines
        ↓
Decision Engine
        ↓
CIO Agent Review
        ↓
Final Recommendation

مع توضيح أن:
- Decision Engine يصدر القرار الحسابي.
- CIO Agent يقدم التفسير النهائي والتوصية للمستخدم.
- لا أحد يستطيع تجاوز Governance.

# 5. Agent Interface

حدد الواجهة الموحدة:

Initialize()
Execute()
Validate()
Explain()
Reset()
Shutdown()

# 6. Memory Rules

حدد:
- Agent Memory ليست ملكية خاصة.
- جميع البيانات المهمة تمر عبر Memory Layer.
- لا Agent يستطيع تعديل تاريخ القرارات.

# 7. Security Rules

وضح:
- Least privilege.
- No autonomous trading.
- No architecture modification.
- No bypassing gates.

# 8. Impact Analysis

وضح تأثير القرار على:
- Architecture
- Development
- Testing
- Deployment

# 9. Status

ضع:

Status: APPROVED (بعد المراجعة)
Version: 1.0.0

لا تعدل أي ملف آخر.
لا تكتب كود.
أنشئ ADR فقط.