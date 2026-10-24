import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "en" | "ar";

const dict = {
  en: {
    app: "DG Compliance & Emergency Response",
    tagline: "Decision support for qualified DG / HSE personnel — not an approval system",
    dashboard: "Dashboard", identify: "DG Identification", verify: "UN Number Verification", imdg: "IMDG Compliance",
    iata: "IATA DGR Compliance", segregation: "Segregation Checker", compat: "Chemical Compatibility",
    sds: "SDS Analyzer", spill: "Spill Response Assistant", erp: "ERP Generator", inspection: "Container Inspection",
    risk: "Risk Assessment", reports: "Reports & Audit Trail", sources: "Regulatory Source Library",
    users: "User & Role Management", login: "Sign in", logout: "Sign out", email: "Email", password: "Password",
    run: "Run check", save: "Save as report", title: "Report title", mode: "Transport mode", status: "Status",
    provisional: "Provisional assessment (against loaded data)", evidence: "Evidence & sources", limitations: "Limitations",
    corrective: "Corrective actions", notes: "Notes", missing: "Missing information", add: "Add", remove: "Remove",
    upload: "Upload", export: "Export", submit: "Submit for review", review: "Mark reviewed", approve: "Approve",
    reject: "Reject", comment: "Comment", demoBanner: "DEMONSTRATION DATA ONLY — no licensed IMDG/IATA content is loaded. Results are provisional and must not be used operationally.",
    language: "العربية", unNumber: "UN number", psn: "Proper Shipping Name", hazardClass: "Class / division",
    subsidiary: "Subsidiary hazards (comma separated)", pg: "Packing group", mp: "Marine pollutant",
    name: "Chemical / trade name", cas: "CAS number", text: "Free text / cargo description",
    generate: "Generate", aiExplain: "AI explanation", loading: "Working…",
  },
  ar: {
    app: "الامتثال للبضائع الخطرة والاستجابة للطوارئ",
    tagline: "أداة دعم قرار للمختصين المؤهلين في البضائع الخطرة والسلامة — وليست نظام اعتماد",
    dashboard: "لوحة التحكم", identify: "تحديد البضائع الخطرة", verify: "التحقق من رقم الأمم المتحدة",
    imdg: "الامتثال للمدونة IMDG", iata: "الامتثال للوائح IATA DGR", segregation: "فحص الفصل",
    compat: "التوافق الكيميائي", sds: "محلل صحيفة بيانات السلامة", spill: "مساعد الاستجابة للانسكاب",
    erp: "مولد خطة الاستجابة للطوارئ", inspection: "فحص الحاويات", risk: "تقييم المخاطر",
    reports: "التقارير وسجل التدقيق", sources: "مكتبة المراجع التنظيمية", users: "إدارة المستخدمين والأدوار",
    login: "تسجيل الدخول", logout: "تسجيل الخروج", email: "البريد الإلكتروني", password: "كلمة المرور",
    run: "تشغيل الفحص", save: "حفظ كتقرير", title: "عنوان التقرير", mode: "وسيلة النقل", status: "الحالة",
    provisional: "تقييم مبدئي (مقابل البيانات المحمّلة)", evidence: "الأدلة والمصادر", limitations: "القيود",
    corrective: "الإجراءات التصحيحية", notes: "ملاحظات", missing: "معلومات ناقصة", add: "إضافة", remove: "حذف",
    upload: "رفع", export: "تصدير", submit: "إرسال للمراجعة", review: "تمت المراجعة", approve: "اعتماد",
    reject: "رفض", comment: "تعليق", demoBanner: "بيانات تجريبية فقط — لم يتم تحميل محتوى مرخّص من IMDG أو IATA. النتائج مبدئية ولا يجوز استخدامها تشغيلياً.",
    language: "English", unNumber: "رقم الأمم المتحدة", psn: "الاسم الرسمي للشحن", hazardClass: "الرتبة / القسم",
    subsidiary: "المخاطر الثانوية (مفصولة بفواصل)", pg: "مجموعة التعبئة", mp: "ملوث بحري",
    name: "الاسم الكيميائي / التجاري", cas: "رقم CAS", text: "نص حر / وصف الشحنة",
    generate: "إنشاء", aiExplain: "شرح بالذكاء الاصطناعي", loading: "جارٍ العمل…",
  },
} as const;

export type Key = keyof (typeof dict)["en"];

const Ctx = createContext<{ lang: Lang; t: (k: Key) => string; toggle: () => void }>({
  lang: "en", t: (k) => dict.en[k], toggle: () => {},
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    try { return (localStorage.getItem("dg_lang") as Lang) || "en"; } catch { return "en"; }
  });
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    try { localStorage.setItem("dg_lang", lang); } catch { /* ignore */ }
  }, [lang]);
  return (
    <Ctx.Provider value={{ lang, t: (k) => dict[lang][k], toggle: () => setLang(lang === "en" ? "ar" : "en") }}>
      {children}
    </Ctx.Provider>
  );
}

export const useI18n = () => useContext(Ctx);
