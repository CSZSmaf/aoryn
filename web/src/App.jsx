import { useEffect, useRef, useState } from "react";
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { siteConfig } from "./config/site";
import { siteCopy } from "./content/copy";
import {
  loadCurrentSession,
  loginAccount,
  logoutAccount,
  registerAccount,
} from "./lib/authApi";

const INITIAL_AUTH_FORM = {
  name: "",
  email: "",
  password: "",
  confirmPassword: "",
  acceptTerms: false,
};

const ROUTE_TO_PAGE_KEY = {
  "/": "home",
  "/product": "product",
  "/workspace": "workspace",
  "/download": "download",
  "/terms": "terms",
  "/privacy": "privacy",
};

function getPreferredLocale() {
  if (typeof window === "undefined") return "zh-CN";
  const stored = window.localStorage.getItem(siteConfig.localeStorageKey);
  return stored === "zh-CN" || stored === "en-US" ? stored : "zh-CN";
}

function getPageKey(pathname) {
  return ROUTE_TO_PAGE_KEY[pathname] || "home";
}

function validateAuthForm(mode, form, validationCopy) {
  const errors = {};
  const trimmedName = form.name.trim();
  const trimmedEmail = form.email.trim();
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (!trimmedEmail) {
    errors.email = validationCopy.emailRequired;
  } else if (!emailPattern.test(trimmedEmail)) {
    errors.email = validationCopy.emailInvalid;
  }

  if (!form.password) {
    errors.password = validationCopy.passwordRequired;
  } else if (form.password.length < 8) {
    errors.password = validationCopy.passwordShort;
  }

  if (mode === "register") {
    if (!trimmedName) {
      errors.name = validationCopy.nameRequired;
    } else if (trimmedName.length < 2) {
      errors.name = validationCopy.nameShort;
    }

    if (!form.confirmPassword) {
      errors.confirmPassword = validationCopy.confirmRequired;
    } else if (form.confirmPassword !== form.password) {
      errors.confirmPassword = validationCopy.confirmMismatch;
    }

    if (!form.acceptTerms) {
      errors.acceptTerms = validationCopy.acceptRequired;
    }
  }

  return errors;
}

function trapFocus(container, event) {
  if (!container || event.key !== "Tab") return;

  const focusable = container.querySelectorAll(
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  );
  if (!focusable.length) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function getRevealStyle(index = 0, baseDelay = 0, step = 80) {
  return { "--reveal-delay": `${baseDelay + index * step}ms` };
}

function SectionHeading({ eyebrow, title, body }) {
  return (
    <div className="section-heading reveal">
      <span className="section-heading__eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      {body ? <p>{body}</p> : null}
    </div>
  );
}

function HomePage({ copy, authenticated, openAuthModal, locale }) {
  const pageCopy = copy.pages.home;
  const isZh = locale === "zh-CN";
  const heroPrimaryLabel = authenticated
    ? (isZh ? "下载桌面版" : "Download desktop app")
    : pageCopy.hero.primaryCta;
  const heroSecondaryLabel = authenticated
    ? (isZh ? "查看界面" : "View workspace")
    : pageCopy.hero.secondaryCta;
  const stageBody = authenticated
    ? (isZh
      ? "桌面工作台负责真实执行，云端只保留最少身份信息与版本分发边界。"
      : "The desktop workspace handles real execution while the cloud keeps only minimal identity and release access boundaries.")
    : pageCopy.stage.body;
  const stageStatus = authenticated
    ? (isZh ? "工作台已就绪" : "Workspace ready")
    : pageCopy.stage.status;
  const cards = authenticated
    ? pageCopy.cards.map((item, index) =>
      index === 2
        ? {
            ...item,
            title: isZh ? "桌面版现已可下载" : "Desktop installer ready",
            body: isZh
              ? "继续下载安装包，或查看工作台与安装说明。"
              : "Continue to the installer or review the workspace and install flow.",
          }
        : item,
    )
    : pageCopy.cards;

  return (
    <>
      <section className="hero-shell">
        <div className="hero-copy reveal" style={getRevealStyle(0, 40, 120)}>
          <span className="section-heading__eyebrow">{pageCopy.hero.eyebrow}</span>
          <h1>{pageCopy.hero.title}</h1>
          <p>{pageCopy.hero.body}</p>
          <div className="button-row">
            <Link className="primary-button" to="/download">
              {heroPrimaryLabel}
            </Link>
            {authenticated ? (
              <Link className="secondary-button" to="/workspace">
                {heroSecondaryLabel}
              </Link>
            ) : (
              <button className="secondary-button" type="button" onClick={() => openAuthModal("register")}>
                {heroSecondaryLabel}
              </button>
            )}
            <Link className="text-link" to="/product">
              {pageCopy.hero.tertiaryCta}
            </Link>
          </div>
        </div>

        <div className="hero-stage reveal" aria-label={pageCopy.stage.title} style={getRevealStyle(1, 120, 120)}>
          <article className="stage-window">
            <div className="stage-window__topbar">
              <div className="brand brand--stage">
                <img src="/aoryn-logo-web-transparent.png" alt="" />
                <div>
                  <strong>{pageCopy.stage.windowLabel}</strong>
                  <span>{pageCopy.stage.windowMeta}</span>
                </div>
              </div>
              <span className="status-pill">{stageStatus}</span>
            </div>

            <div className="stage-window__body">
              <aside className="stage-window__rail">
                <span>{pageCopy.stage.railLabel}</span>
                <ul>
                  {pageCopy.stage.railItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </aside>

              <div className="stage-window__content">
                <div className="chip-row">
                  {pageCopy.stage.chips.map((chip) => (
                    <span className="chip" key={chip}>
                      {chip}
                    </span>
                  ))}
                </div>

                <div className="stage-window__focus">
                  <span>{pageCopy.stage.focusLabel}</span>
                  <strong>{pageCopy.stage.focusTitle}</strong>
                  <p>{stageBody}</p>
                </div>

                <div className="metric-row">
                  {pageCopy.stage.metrics.map((item, index) => (
                    <article className="metric-card" key={item.label} style={getRevealStyle(index, 220, 70)}>
                      <strong>{item.value}</strong>
                      <span>{item.label}</span>
                    </article>
                  ))}
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="section-shell section-shell--compact">
        <div className="feature-grid">
          {cards.map((item, index) => (
            <Link className="feature-card reveal" to={item.href} key={item.title} style={getRevealStyle(index, 80, 90)}>
              <span className="feature-card__index">{String(index + 1).padStart(2, "0")}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </Link>
          ))}
        </div>
      </section>

      {!authenticated ? (
        <section className="section-shell">
          <article className="cta-band reveal" style={getRevealStyle(0, 100)}>
            <div>
              <span className="section-heading__eyebrow">{pageCopy.cta.eyebrow}</span>
              <h2>{pageCopy.cta.title}</h2>
              <p>{pageCopy.cta.body}</p>
            </div>
            <div className="button-row">
              <Link className="primary-button" to="/download">
                {pageCopy.cta.primaryCta}
              </Link>
              <button className="secondary-button" type="button" onClick={() => openAuthModal("login")}>
                {pageCopy.cta.secondaryCta}
              </button>
            </div>
          </article>
        </section>
      ) : null}
    </>
  );
}

function ProductPage({ copy }) {
  const pageCopy = copy.pages.product;

  return (
    <>
      <section className="detail-hero detail-hero--single reveal" style={getRevealStyle(0, 30)}>
        <div className="detail-hero__copy">
          <span className="section-heading__eyebrow">{pageCopy.hero.eyebrow}</span>
          <h1>{pageCopy.hero.title}</h1>
          <p>{pageCopy.hero.body}</p>
        </div>
      </section>

      <section className="section-shell">
        <SectionHeading
          eyebrow={pageCopy.pillars.eyebrow}
          title={pageCopy.pillars.title}
          body={pageCopy.pillars.body}
        />
        <div className="detail-grid detail-grid--three detail-grid--pillars">
          {pageCopy.pillars.items.map((item, index) => (
            <article className="detail-card reveal" key={item.title} style={getRevealStyle(index, 40, 80)}>
              <span className="detail-card__eyebrow">{item.note}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-shell">
        <SectionHeading
          eyebrow={pageCopy.workflow.eyebrow}
          title={pageCopy.workflow.title}
          body={pageCopy.workflow.body}
        />
        <div className="detail-grid detail-grid--steps detail-grid--workflow">
          {pageCopy.workflow.items.map((item, index) => (
            <article className="detail-card detail-card--step reveal" key={item.title} style={getRevealStyle(index, 40, 90)}>
              <span className="detail-card__eyebrow">{item.step}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function WorkspacePage({ copy, authenticated, locale }) {
  const pageCopy = copy.pages.workspace;
  const heroBody = authenticated
    ? (locale === "zh-CN"
      ? "进入可见的桌面执行界面，把对话、执行与回放整理进同一个工作台。"
      : "Open the visible desktop workspace and keep chat, execution, and replay inside one surface.")
    : pageCopy.hero.body;

  return (
    <>
      <section className="detail-hero detail-hero--single reveal" style={getRevealStyle(0, 30)}>
        <div className="detail-hero__copy">
          <span className="section-heading__eyebrow">{pageCopy.hero.eyebrow}</span>
          <h1>{pageCopy.hero.title}</h1>
          <p>{heroBody}</p>
        </div>
      </section>

      <section className="section-shell">
        <article className="workspace-stage reveal" style={getRevealStyle(0, 70)}>
          <div className="workspace-stage__copy">
            <span className="section-heading__eyebrow">{pageCopy.preview.eyebrow}</span>
            <h2>{pageCopy.preview.title}</h2>
            <p>{pageCopy.preview.body}</p>
          </div>
          <div className="metric-row metric-row--wide workspace-stage__metrics">
            {pageCopy.preview.cards.map((item, index) => (
              <article className="metric-card metric-card--soft" key={item.label} style={getRevealStyle(index, 150, 80)}>
                <strong>{item.value}</strong>
                <span>{item.label}</span>
              </article>
            ))}
          </div>
        </article>
      </section>

      <section className="section-shell">
        <div className="detail-grid detail-grid--three detail-grid--workspace">
          {pageCopy.sections.map((item, index) => (
            <article className="detail-card reveal" key={item.title} style={getRevealStyle(index, 40, 80)}>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function DownloadPage({ copy, authState, authReady, openAuthModal, locale }) {
  const pageCopy = copy.pages.download;
  const canDownload = authReady && authState.authenticated;
  const unlockedBody = locale === "zh-CN"
    ? "桌面安装包现已可用。任务、截图、历史与配置仍保留在本地设备，不会上传到云端。"
    : "The desktop installer is ready. Tasks, screenshots, history, and config stay on your device and are not uploaded to the cloud.";
  const packageMeta = [
    { label: pageCopy.packageMeta.version, value: siteConfig.release.version },
    { label: pageCopy.packageMeta.platform, value: siteConfig.release.platform },
    { label: pageCopy.packageMeta.size, value: siteConfig.release.fileSize },
    { label: pageCopy.packageMeta.format, value: siteConfig.release.packageType },
  ];

  return (
    <>
      {canDownload ? (
        <section className="section-shell section-shell--download-top">
          <article className="download-gate reveal is-unlocked" style={getRevealStyle(0, 40)}>
            <div className="download-gate__content">
              <span className="section-heading__eyebrow">{pageCopy.unlocked.eyebrow}</span>
              <h2>{pageCopy.unlocked.title}</h2>
              <p>{unlockedBody}</p>
            </div>

            <div className="button-row">
              <a className="primary-button" href={siteConfig.release.protectedDownloadPath}>
                {pageCopy.unlocked.primaryCta}
              </a>
            </div>
          </article>
        </section>
      ) : (
        <section className="detail-hero detail-hero--download reveal" style={getRevealStyle(0, 30)}>
          <div className="detail-hero__copy">
            <span className="section-heading__eyebrow">{pageCopy.hero.eyebrow}</span>
            <h1>{pageCopy.hero.title}</h1>
            <p>{pageCopy.hero.body}</p>
          </div>

          <article className="download-gate is-locked">
            <div className="download-gate__content">
              <span className="section-heading__eyebrow">{pageCopy.locked.eyebrow}</span>
              <h2>{pageCopy.locked.title}</h2>
              <p>{pageCopy.locked.body}</p>
            </div>

            <div className="button-row">
              <button className="primary-button" type="button" onClick={() => openAuthModal("login")}>
                {pageCopy.locked.primaryCta}
              </button>
            </div>
          </article>
        </section>
      )}

      <section className="section-shell section-shell--compact">
        <div className="download-meta-grid">
          {packageMeta.map((item, index) => (
            <article className="download-meta-card reveal" key={item.label} style={getRevealStyle(index, 50, 70)}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </article>
          ))}
        </div>
      </section>

      {!canDownload ? (
        <>
          <section className="section-shell">
            <SectionHeading
              eyebrow={pageCopy.steps.eyebrow}
              title={pageCopy.steps.title}
              body={pageCopy.steps.body}
            />
            <div className="detail-grid detail-grid--three detail-grid--download-steps">
              {pageCopy.steps.items.map((item, index) => (
                <article className="detail-card detail-card--step reveal" key={item.title} style={getRevealStyle(index, 40, 80)}>
                  <span className="detail-card__eyebrow">{item.step}</span>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="section-shell">
            <SectionHeading
              eyebrow={pageCopy.faq.eyebrow}
              title={pageCopy.faq.title}
              body={pageCopy.faq.body}
            />
            <div className="faq-list">
              {pageCopy.faq.items.map((item, index) => (
                <details className="faq-item reveal" key={item.question} style={getRevealStyle(index, 40, 70)}>
                  <summary>{item.question}</summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}

function LegalPage({ pageCopy }) {
  return (
    <>
      <section className="detail-hero detail-hero--single reveal" style={getRevealStyle(0, 30)}>
        <div className="detail-hero__copy">
          <span className="section-heading__eyebrow">{pageCopy.hero.eyebrow}</span>
          <h1>{pageCopy.hero.title}</h1>
          <p>{pageCopy.hero.body}</p>
        </div>
      </section>

      <section className="section-shell">
        <div className="legal-stack">
          {pageCopy.sections.map((item, index) => (
            <article className="legal-card reveal" key={item.title} style={getRevealStyle(index, 40, 90)}>
              <h2>{item.title}</h2>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function AuthModal({
  copy,
  mode,
  setMode,
  form,
  errors,
  isSubmitting,
  submitFeedback,
  closeModal,
  handleSubmit,
  updateField,
  modalRef,
  firstInputRef,
  fieldRefs,
}) {
  const fieldCopy = copy.auth.fields;
  const isRegister = mode === "register";
  const signalChips = copy.pages.home.stage.chips.slice(0, 3);

  return (
    <div className="modal-shell" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}>
      <div className="modal-card auth-modal" ref={modalRef} role="dialog" aria-modal="true" aria-labelledby="auth-modal-title">
        <div className="auth-modal__intro">
          <span className="section-heading__eyebrow">{copy.brandDescriptor}</span>
          <h2>{isRegister ? copy.auth.registerTitle : copy.auth.loginTitle}</h2>
          <p>{copy.auth.dialogBody}</p>
          <div className="auth-modal__signals">
            {signalChips.map((chip) => (
              <span className="auth-modal__signal" key={chip}>
                {chip}
              </span>
            ))}
          </div>
        </div>

        <div className="auth-modal__panel">
        <div className="modal-card__head">
          <div>
            <span className="section-heading__eyebrow">
              {isRegister ? copy.auth.registerTitle : copy.auth.loginTitle}
            </span>
            <h2 id="auth-modal-title">{copy.auth.dialogTitle}</h2>
          </div>
          <button className="icon-button" type="button" onClick={closeModal} aria-label={copy.nav.closeMenu}>
            ×
          </button>
        </div>

        <p className="modal-card__body">{copy.auth.dialogBody}</p>

        <div className="auth-tabs" role="tablist" aria-label={copy.auth.dialogTitle}>
          <button
            className={mode === "login" ? "auth-tab auth-tab--active" : "auth-tab"}
            type="button"
            onClick={() => setMode("login")}
          >
            {copy.auth.tabs.login}
          </button>
          <button
            className={mode === "register" ? "auth-tab auth-tab--active" : "auth-tab"}
            type="button"
            onClick={() => setMode("register")}
          >
            {copy.auth.tabs.register}
          </button>
        </div>

        <form className="register-form" onSubmit={handleSubmit} noValidate>
          {isRegister ? (
            <label className="field">
              <span>{fieldCopy.name}</span>
              <input
                ref={(node) => {
                  firstInputRef.current = node;
                  fieldRefs.current.name = node;
                }}
                type="text"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder={fieldCopy.namePlaceholder}
                aria-invalid={Boolean(errors.name)}
              />
              {errors.name ? <small className="field-error">{errors.name}</small> : null}
            </label>
          ) : null}

          <label className="field">
            <span>{fieldCopy.email}</span>
            <input
              ref={(node) => {
                if (!isRegister) firstInputRef.current = node;
                fieldRefs.current.email = node;
              }}
              type="email"
              value={form.email}
              onChange={(event) => updateField("email", event.target.value)}
              placeholder={fieldCopy.emailPlaceholder}
              aria-invalid={Boolean(errors.email)}
            />
            {errors.email ? <small className="field-error">{errors.email}</small> : null}
          </label>

          <label className="field">
            <span>{fieldCopy.password}</span>
            <input
              ref={(node) => {
                fieldRefs.current.password = node;
              }}
              type="password"
              value={form.password}
              onChange={(event) => updateField("password", event.target.value)}
              placeholder={fieldCopy.passwordPlaceholder}
              aria-invalid={Boolean(errors.password)}
            />
            {errors.password ? <small className="field-error">{errors.password}</small> : null}
          </label>

          {isRegister ? (
            <>
              <label className="field">
                <span>{fieldCopy.confirmPassword}</span>
                <input
                  ref={(node) => {
                    fieldRefs.current.confirmPassword = node;
                  }}
                  type="password"
                  value={form.confirmPassword}
                  onChange={(event) => updateField("confirmPassword", event.target.value)}
                  placeholder={fieldCopy.confirmPasswordPlaceholder}
                  aria-invalid={Boolean(errors.confirmPassword)}
                />
                {errors.confirmPassword ? <small className="field-error">{errors.confirmPassword}</small> : null}
              </label>

              <label className="checkbox-field">
                <input
                  ref={(node) => {
                    fieldRefs.current.acceptTerms = node;
                  }}
                  type="checkbox"
                  checked={form.acceptTerms}
                  onChange={(event) => updateField("acceptTerms", event.target.checked)}
                />
                <span>
                  {fieldCopy.acceptTermsPrefix}{" "}
                  <Link to="/terms" onClick={closeModal}>
                    {fieldCopy.acceptTermsLink}
                  </Link>{" "}
                  {fieldCopy.acceptPrivacyMiddle}{" "}
                  <Link to="/privacy" onClick={closeModal}>
                    {fieldCopy.acceptPrivacyLink}
                  </Link>
                </span>
              </label>
              {errors.acceptTerms ? <small className="field-error">{errors.acceptTerms}</small> : null}
            </>
          ) : null}

          {submitFeedback.message ? (
            <div className={`form-feedback form-feedback--${submitFeedback.tone}`} role="status" aria-live="polite">
              {submitFeedback.message}
            </div>
          ) : null}

          <div className="modal-card__actions">
            <button className="secondary-button" type="button" onClick={closeModal}>
              {copy.nav.closeMenu}
            </button>
            <button className="primary-button" type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? copy.auth.submitBusy
                : isRegister
                  ? copy.auth.registerButton
                  : copy.auth.loginButton}
            </button>
          </div>
        </form>
        </div>
      </div>
    </div>
  );
}

function AppFrame() {
  const [locale, setLocale] = useState(getPreferredLocale);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [form, setForm] = useState(INITIAL_AUTH_FORM);
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitFeedback, setSubmitFeedback] = useState({ tone: "", message: "" });
  const [authState, setAuthState] = useState({
    loading: true,
    authenticated: false,
    user: null,
    profile: null,
  });

  const modalRef = useRef(null);
  const firstInputRef = useRef(null);
  const fieldRefs = useRef({});
  const lastActiveElementRef = useRef(null);

  const location = useLocation();
  const copy = siteCopy[locale] || siteCopy["zh-CN"];
  const pageKey = getPageKey(location.pathname);
  const pageCopy = copy.pages[pageKey] || copy.pages.home;
  const currentYear = new Date().getFullYear();

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        const payload = await loadCurrentSession(siteConfig.auth.meEndpoint);
        if (!cancelled) {
          setAuthState({
            loading: false,
            authenticated: Boolean(payload.authenticated),
            user: payload.user || null,
            profile: payload.profile || null,
          });
        }
      } catch {
        if (!cancelled) {
          setAuthState({
            loading: false,
            authenticated: false,
            user: null,
            profile: null,
          });
        }
      }
    }
    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = pageCopy.meta.title;
    window.localStorage.setItem(siteConfig.localeStorageKey, locale);

    const metaDescription = document.querySelector('meta[name="description"]');
    metaDescription?.setAttribute("content", pageCopy.meta.description);
  }, [locale, pageCopy.meta.description, pageCopy.meta.title]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    setIsMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll(".reveal"));
    if (!nodes.length) return undefined;

    const reducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reducedMotion || typeof IntersectionObserver === "undefined") {
      nodes.forEach((node) => node.classList.add("is-visible"));
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.18, rootMargin: "0px 0px -8% 0px" },
    );

    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [locale, location.pathname]);

  useEffect(() => {
    if (isAuthOpen) return;
    const previous = lastActiveElementRef.current;
    if (previous && typeof previous.focus === "function") {
      window.requestAnimationFrame(() => previous.focus());
    }
  }, [isAuthOpen]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    if (isAuthOpen || isMenuOpen) {
      document.body.style.overflow = "hidden";
    }

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        if (isAuthOpen) {
          setIsAuthOpen(false);
        } else if (isMenuOpen) {
          setIsMenuOpen(false);
        }
      } else if (isAuthOpen) {
        trapFocus(modalRef.current, event);
      }
    };

    if (isAuthOpen || isMenuOpen) {
      window.addEventListener("keydown", handleKeyDown);
    }

    if (isAuthOpen) {
      window.requestAnimationFrame(() => {
        firstInputRef.current?.focus();
      });
    }

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isAuthOpen, isMenuOpen]);

  function toggleLocale() {
    setLocale((current) => (current === "zh-CN" ? "en-US" : "zh-CN"));
  }

  function openAuthModal(mode = "login") {
    lastActiveElementRef.current = document.activeElement;
    setAuthMode(mode);
    setForm(INITIAL_AUTH_FORM);
    setErrors({});
    setSubmitFeedback({ tone: "", message: "" });
    setIsMenuOpen(false);
    setIsAuthOpen(true);
  }

  function closeAuthModal() {
    setIsAuthOpen(false);
  }

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  async function handleAuthSubmit(event) {
    event.preventDefault();
    const validationErrors = validateAuthForm(authMode, form, copy.auth.validation);
    if (Object.keys(validationErrors).length) {
      setErrors(validationErrors);
      setSubmitFeedback({ tone: "error", message: "" });
      const firstInvalidField = Object.keys(validationErrors)[0];
      fieldRefs.current[firstInvalidField]?.focus?.();
      return;
    }

    setIsSubmitting(true);
    setSubmitFeedback({ tone: "", message: "" });

    try {
      if (authMode === "register") {
        const registerEmail = form.email.trim();
        const payload = await registerAccount(siteConfig.auth.registerEndpoint, {
          displayName: form.name.trim(),
          email: registerEmail,
          password: form.password,
        });
        setAuthMode("login");
        setForm({
          ...INITIAL_AUTH_FORM,
          email: registerEmail,
        });
        setErrors({});
        setSubmitFeedback({
          tone: "success",
          message: payload.message || copy.auth.messages.registerSuccess,
        });
        window.requestAnimationFrame(() => {
          fieldRefs.current.password?.focus?.();
        });
      } else {
        await loginAccount(siteConfig.auth.loginEndpoint, {
          email: form.email.trim(),
          password: form.password,
        });
        const payload = await loadCurrentSession(siteConfig.auth.meEndpoint);
        setAuthState({
          loading: false,
          authenticated: Boolean(payload.authenticated),
          user: payload.user || null,
          profile: payload.profile || null,
        });
        if (!payload.authenticated) {
          throw new Error(copy.auth.messages.networkError);
        }
        setForm(INITIAL_AUTH_FORM);
        setErrors({});
        setSubmitFeedback({
          tone: "success",
          message: payload.message || copy.auth.messages.loginSuccess,
        });
        window.setTimeout(() => {
          setIsAuthOpen(false);
        }, 120);
      }
    } catch (error) {
      setSubmitFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : copy.auth.messages.networkError,
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleLogout() {
    try {
      const payload = await logoutAccount(siteConfig.auth.logoutEndpoint);
      setAuthState({
        loading: false,
        authenticated: false,
        user: null,
        profile: null,
      });
      setSubmitFeedback({
        tone: "success",
        message: payload.message || copy.auth.messages.logoutSuccess,
      });
    } catch (error) {
      setSubmitFeedback({
        tone: "error",
        message: error instanceof Error ? error.message : copy.auth.messages.networkError,
      });
    }
  }

  const navItems = [
    { to: "/product", label: copy.nav.product },
    { to: "/workspace", label: copy.nav.workspace },
    { to: "/download", label: copy.nav.download },
  ];

  const accountLabel =
    String(authState.profile?.display_name || authState.user?.email || "").trim() ||
    copy.auth.signedOut;

  return (
    <div className="site-shell">
      <div className="site-shell__glow site-shell__glow--left" />
      <div className="site-shell__glow site-shell__glow--right" />

      <header className="topbar">
        <Link className="brand" to="/" aria-label={siteConfig.siteName}>
          <img src="/aoryn-logo-web-transparent.png" alt="" />
          <div>
            <strong>{siteConfig.siteName}</strong>
            <span>{copy.brandDescriptor}</span>
          </div>
        </Link>

        <nav className="topnav" aria-label="Primary">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? "topnav__link topnav__link--active" : "topnav__link"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="topbar-actions">
          <button className="ghost-button" type="button" onClick={toggleLocale}>
            {copy.langSwitch}
          </button>
          {authState.authenticated ? (
            <>
              <span className="account-chip" title={accountLabel}>
                {copy.nav.account}: {accountLabel}
              </span>
              <button className="secondary-button secondary-button--nav" type="button" onClick={handleLogout}>
                {copy.nav.logout}
              </button>
            </>
          ) : (
            <>
              <button className="ghost-button" type="button" onClick={() => openAuthModal("login")}>
                {copy.nav.login}
              </button>
              <button className="secondary-button secondary-button--nav" type="button" onClick={() => openAuthModal("register")}>
                {copy.nav.register}
              </button>
            </>
          )}
          <button
            className="menu-button"
            type="button"
            onClick={() => setIsMenuOpen((current) => !current)}
            aria-expanded={isMenuOpen}
            aria-label={isMenuOpen ? copy.nav.closeMenu : copy.nav.menu}
          >
            <span />
            <span />
          </button>
        </div>
      </header>

      {isMenuOpen ? (
        <div className="mobile-menu-shell" onMouseDown={(event) => event.target === event.currentTarget && setIsMenuOpen(false)}>
          <div className="mobile-menu">
            <div className="mobile-menu__head">
              <strong>{siteConfig.siteName}</strong>
              <button className="icon-button" type="button" onClick={() => setIsMenuOpen(false)} aria-label={copy.nav.closeMenu}>
                ×
              </button>
            </div>

            <div className="mobile-menu__links">
              <Link className="mobile-menu__link" to="/">
                {copy.nav.home}
              </Link>
              {navItems.map((item) => (
                <Link className="mobile-menu__link" key={item.to} to={item.to}>
                  {item.label}
                </Link>
              ))}
              <Link className="mobile-menu__link" to="/terms">
                {copy.nav.terms}
              </Link>
              <Link className="mobile-menu__link" to="/privacy">
                {copy.nav.privacy}
              </Link>
            </div>

            <div className="mobile-menu__actions">
              <button className="ghost-button" type="button" onClick={toggleLocale}>
                {copy.langSwitch}
              </button>
              {authState.authenticated ? (
                <button className="primary-button" type="button" onClick={handleLogout}>
                  {copy.nav.logout}
                </button>
              ) : (
                <button className="primary-button" type="button" onClick={() => openAuthModal("login")}>
                  {copy.nav.login}
                </button>
              )}
            </div>
          </div>
        </div>
      ) : null}

      <main className={`page-root page-root--${pageKey}`}>
        <Routes>
          <Route
            path="/"
            element={
              <HomePage
                copy={copy}
                authenticated={authState.authenticated}
                openAuthModal={openAuthModal}
                locale={locale}
              />
            }
          />
          <Route path="/product" element={<ProductPage copy={copy} />} />
          <Route path="/workspace" element={<WorkspacePage copy={copy} authenticated={authState.authenticated} locale={locale} />} />
          <Route
            path="/download"
            element={
              <DownloadPage
                copy={copy}
                authState={authState}
                authReady={!authState.loading}
                openAuthModal={openAuthModal}
                locale={locale}
              />
            }
          />
          <Route path="/terms" element={<LegalPage pageCopy={copy.pages.terms} />} />
          <Route path="/privacy" element={<LegalPage pageCopy={copy.pages.privacy} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="site-footer">
        <div className="site-footer__brand">
          <strong>{siteConfig.siteName}</strong>
          <p>{copy.footer.tagline}</p>
        </div>

        <div className="site-footer__links">
          <Link to="/product">{copy.nav.product}</Link>
          <Link to="/workspace">{copy.nav.workspace}</Link>
          <Link to="/download">{copy.nav.download}</Link>
          <Link to="/terms">{copy.nav.terms}</Link>
          <Link to="/privacy">{copy.nav.privacy}</Link>
        </div>

        <p className="site-footer__copyright">
          © {currentYear} {copy.footer.copyright}
        </p>
      </footer>

      {isAuthOpen ? (
        <AuthModal
          copy={copy}
          mode={authMode}
          setMode={setAuthMode}
          form={form}
          errors={errors}
          isSubmitting={isSubmitting}
          submitFeedback={submitFeedback}
          closeModal={closeAuthModal}
          handleSubmit={handleAuthSubmit}
          updateField={updateField}
          modalRef={modalRef}
          firstInputRef={firstInputRef}
          fieldRefs={fieldRefs}
        />
      ) : null}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppFrame />
    </BrowserRouter>
  );
}
