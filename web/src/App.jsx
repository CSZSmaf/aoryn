import { startTransition, useEffect, useRef, useState } from "react";
import { siteConfig } from "./config/site";
import { siteCopy } from "./content/copy";
import { submitRegistration } from "./lib/submitRegistration";

const INITIAL_FORM = {
  name: "",
  email: "",
  password: "",
  confirmPassword: "",
  acceptTerms: false,
};

function getPreferredLocale() {
  if (typeof window === "undefined") return "en-US";
  const stored = window.localStorage.getItem(siteConfig.localeStorageKey);
  if (stored === "zh-CN" || stored === "en-US") return stored;
  return window.navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US";
}

function validateRegistration(form, validationCopy) {
  const errors = {};
  const trimmedName = form.name.trim();
  const trimmedEmail = form.email.trim();
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  if (!trimmedName) {
    errors.name = validationCopy.nameRequired;
  } else if (trimmedName.length < 2) {
    errors.name = validationCopy.nameShort;
  }

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

  if (!form.confirmPassword) {
    errors.confirmPassword = validationCopy.confirmRequired;
  } else if (form.confirmPassword !== form.password) {
    errors.confirmPassword = validationCopy.confirmMismatch;
  }

  if (!form.acceptTerms) {
    errors.acceptTerms = validationCopy.acceptRequired;
  }

  return errors;
}

function trapFocus(container, event) {
  if (!container || event.key !== "Tab") return;
  const focusable = container.querySelectorAll(
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
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

function ProductPreview({ copy }) {
  return (
    <div className="hero-preview reveal" aria-label={copy.windowLabel}>
      <div className="preview-shell">
        <div className="preview-topbar">
          <div className="preview-brand">
            <img src="/logo-mark.svg" alt="" />
            <span>{copy.windowLabel}</span>
          </div>
          <span className="status-pill">{copy.status}</span>
        </div>

        <div className="preview-grid">
          <div className="preview-column preview-column--stack">
            {copy.cards.map((item) => (
              <article className="preview-card" key={item.label}>
                <span className="preview-label">{item.label}</span>
                <strong>{item.value}</strong>
              </article>
            ))}
          </div>

          <div className="preview-column">
            <article className="preview-terminal">
              <span className="preview-label">{copy.timelineTitle}</span>
              <ol>
                {copy.timeline.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ol>
            </article>

            <article className="preview-window">
              <div className="preview-window__chrome">
                <span />
                <span />
                <span />
              </div>
              <div className="preview-window__body">
                <div className="preview-chip-row">
                  {copy.chips.map((item) => (
                    <span className="preview-chip" key={item}>
                      {item}
                    </span>
                  ))}
                </div>
                <div className="preview-panel">
                  <strong>{copy.panelTitle}</strong>
                  <p>{copy.panelBody}</p>
                </div>
                <div className="preview-metrics">
                  {copy.metrics.map((item) => (
                    <div key={`${item.value}-${item.label}`}>
                      <strong>{item.value}</strong>
                      <span>{item.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </article>
          </div>
        </div>
      </div>
    </div>
  );
}

function SectionHeading({ eyebrow, title, body }) {
  return (
    <div className="section-heading reveal">
      <span className="section-eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      {body ? <p>{body}</p> : null}
    </div>
  );
}

export default function App() {
  const [locale, setLocale] = useState(getPreferredLocale);
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitFeedback, setSubmitFeedback] = useState({ tone: "", message: "" });
  const modalRef = useRef(null);
  const firstInputRef = useRef(null);
  const fieldRefs = useRef({});
  const lastActiveElementRef = useRef(null);

  const copy = siteCopy[locale] || siteCopy["en-US"];
  const currentYear = new Date().getFullYear();

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = `${siteConfig.siteName} | ${copy.hero.eyebrow}`;
    window.localStorage.setItem(siteConfig.localeStorageKey, locale);
  }, [copy.hero.eyebrow, locale]);

  useEffect(() => {
    if (isRegisterOpen) return;
    const previous = lastActiveElementRef.current;
    if (previous && typeof previous.focus === "function") {
      window.requestAnimationFrame(() => previous.focus());
    }
  }, [isRegisterOpen]);

  useEffect(() => {
    if (!isRegisterOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setIsRegisterOpen(false);
      } else {
        trapFocus(modalRef.current, event);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.requestAnimationFrame(() => {
      firstInputRef.current?.focus();
    });

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isRegisterOpen]);

  const toggleLocale = () => {
    startTransition(() => {
      setLocale((current) => (current === "zh-CN" ? "en-US" : "zh-CN"));
    });
  };

  const openRegisterModal = (event) => {
    lastActiveElementRef.current = event?.currentTarget || document.activeElement;
    setForm(INITIAL_FORM);
    setErrors({});
    setSubmitFeedback({ tone: "", message: "" });
    setIsRegisterOpen(true);
  };

  const closeRegisterModal = () => {
    setIsRegisterOpen(false);
  };

  const updateField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const validationErrors = validateRegistration(form, copy.register.validation);

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
      const response = await submitRegistration({
        endpoint: siteConfig.registration.endpoint,
        payload: {
          name: form.name.trim(),
          email: form.email.trim(),
          password: form.password,
        },
        locale,
        messages: copy.register.form,
      });

      setForm(INITIAL_FORM);
      setErrors({});
      setSubmitFeedback({
        tone: "success",
        message: response.message,
      });
    } catch (error) {
      setSubmitFeedback({
        tone: "error",
        message: error.message || copy.register.form.networkError,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="site-shell">
      <div className="site-orb site-orb--left" />
      <div className="site-orb site-orb--right" />

      <header className="topbar">
        <a className="brand" href="#top" aria-label={siteConfig.siteName}>
          <img src="/logo-mark.svg" alt="" />
          <div>
            <strong>{siteConfig.siteName}</strong>
            <span>{siteConfig.domain}</span>
          </div>
        </a>

        <nav className="topnav" aria-label="Primary">
          <a href="#product">{copy.nav.product}</a>
          <a href="#workflow">{copy.nav.workflow}</a>
          <a href="#download">{copy.nav.download}</a>
          <a href="#faq">{copy.nav.faq}</a>
        </nav>

        <div className="topbar-actions">
          <button className="ghost-button" type="button" onClick={toggleLocale}>
            {copy.langSwitch}
          </button>
          <button className="primary-button" type="button" onClick={openRegisterModal}>
            {copy.nav.register}
          </button>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="hero-copy reveal">
            <span className="announcement-pill">{copy.announcement}</span>
            <span className="hero-eyebrow">
              {siteConfig.siteName} {siteConfig.release.version} · {copy.hero.eyebrow}
            </span>
            <h1>{copy.hero.title}</h1>
            <p className="hero-body">{copy.hero.body}</p>

            <div className="hero-actions">
              <a
                className="primary-button"
                href={siteConfig.release.downloadUrl}
                target="_blank"
                rel="noreferrer"
              >
                {copy.hero.primaryCta}
              </a>
              <button className="secondary-button" type="button" onClick={openRegisterModal}>
                {copy.hero.secondaryCta}
              </button>
            </div>

            <p className="hero-note">{copy.hero.availability}</p>

            <div className="hero-stats">
              {copy.hero.stats.map((item) => (
                <article className="stat-card" key={item.value}>
                  <strong>{item.value}</strong>
                  <span>{item.label}</span>
                </article>
              ))}
            </div>

            <ul className="hero-proof">
              {copy.hero.proof.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>

          <ProductPreview copy={copy.preview} />
        </section>

        <section className="content-section" id="product">
          <SectionHeading eyebrow={copy.product.eyebrow} title={copy.product.title} body={copy.product.body} />
          <div className="feature-grid">
            {copy.product.items.map((item) => (
              <article className="feature-card reveal" key={item.title}>
                <span className="card-kicker">{siteConfig.siteName}</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="content-section content-section--contrast">
          <SectionHeading eyebrow={copy.difference.eyebrow} title={copy.difference.title} />
          <div className="difference-grid">
            {copy.difference.items.map((item) => (
              <article className="difference-card reveal" key={item.title}>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="content-section" id="workflow">
          <SectionHeading eyebrow={copy.workflow.eyebrow} title={copy.workflow.title} />
          <div className="workflow-grid">
            {copy.workflow.steps.map((item, index) => (
              <article className="workflow-card reveal" key={item.title}>
                <span className="workflow-index">0{index + 1}</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="content-section content-section--download" id="download">
          <SectionHeading eyebrow={copy.download.eyebrow} title={copy.download.title} body={copy.download.body} />

          <div className="download-layout">
            <article className="download-card reveal">
              <div className="download-card__head">
                <div>
                  <span className="card-kicker">{siteConfig.release.channel}</span>
                  <h3>{siteConfig.release.fileName}</h3>
                </div>
                <span className="status-pill status-pill--dark">{siteConfig.release.version}</span>
              </div>

              <div className="download-meta">
                <div>
                  <span>{copy.download.labels.version}</span>
                  <strong>{siteConfig.release.version}</strong>
                </div>
                <div>
                  <span>{copy.download.labels.platform}</span>
                  <strong>{siteConfig.release.platform}</strong>
                </div>
                <div>
                  <span>{copy.download.labels.packageType}</span>
                  <strong>{siteConfig.release.packageType}</strong>
                </div>
                <div>
                  <span>{copy.download.labels.fileSize}</span>
                  <strong>{siteConfig.release.fileSize}</strong>
                </div>
                <div>
                  <span>{copy.download.labels.hosting}</span>
                  <strong>{siteConfig.release.hosting}</strong>
                </div>
              </div>

              <div className="download-actions">
                <a
                  className="primary-button"
                  href={siteConfig.release.downloadUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {copy.download.primaryCta}
                </a>
                <button className="secondary-button" type="button" onClick={openRegisterModal}>
                  {copy.download.secondaryCta}
                </button>
              </div>
            </article>

            <aside className="download-notes reveal">
              <h3>{siteConfig.siteName}</h3>
              <ul>
                {copy.download.notes.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </aside>
          </div>
        </section>

        <section className="content-section">
          <div className="account-cta reveal">
            <div>
              <span className="section-eyebrow">{copy.register.eyebrow}</span>
              <h2>{copy.register.title}</h2>
              <p>{copy.register.body}</p>
            </div>

            <div className="account-cta__side">
              <ul>
                {copy.register.benefits.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <button className="primary-button" type="button" onClick={openRegisterModal}>
                {copy.register.cta}
              </button>
            </div>
          </div>
        </section>

        <section className="content-section" id="faq">
          <SectionHeading eyebrow={copy.faq.eyebrow} title={copy.faq.title} />
          <div className="faq-list">
            {copy.faq.items.map((item) => (
              <details className="faq-item reveal" key={item.question}>
                <summary>{item.question}</summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div>
          <strong>{siteConfig.siteName}</strong>
          <p>{copy.footer.tagline}</p>
        </div>
        <p>
          © {currentYear} {copy.footer.copyright}
        </p>
      </footer>

      {isRegisterOpen ? (
        <div className="modal-shell" onMouseDown={(event) => event.target === event.currentTarget && closeRegisterModal()}>
          <div
            className="modal-card"
            ref={modalRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="register-modal-title"
          >
            <div className="modal-card__head">
              <div>
                <span className="section-eyebrow">{copy.register.eyebrow}</span>
                <h2 id="register-modal-title">{copy.register.modalTitle}</h2>
              </div>
              <button className="icon-button" type="button" onClick={closeRegisterModal} aria-label={copy.register.form.close}>
                ×
              </button>
            </div>

            <p className="modal-card__body">{copy.register.modalBody}</p>

            <form className="register-form" onSubmit={handleSubmit} noValidate>
              <label className="field">
                <span>{copy.register.form.name}</span>
                <input
                  ref={(node) => {
                    firstInputRef.current = node;
                    fieldRefs.current.name = node;
                  }}
                  type="text"
                  value={form.name}
                  onChange={(event) => updateField("name", event.target.value)}
                  placeholder={copy.register.form.namePlaceholder}
                  aria-invalid={Boolean(errors.name)}
                />
                {errors.name ? <small className="field-error">{errors.name}</small> : null}
              </label>

              <label className="field">
                <span>{copy.register.form.email}</span>
                <input
                  ref={(node) => {
                    fieldRefs.current.email = node;
                  }}
                  type="email"
                  value={form.email}
                  onChange={(event) => updateField("email", event.target.value)}
                  placeholder={copy.register.form.emailPlaceholder}
                  aria-invalid={Boolean(errors.email)}
                />
                {errors.email ? <small className="field-error">{errors.email}</small> : null}
              </label>

              <div className="field-row">
                <label className="field">
                  <span>{copy.register.form.password}</span>
                  <input
                    ref={(node) => {
                      fieldRefs.current.password = node;
                    }}
                    type="password"
                    value={form.password}
                    onChange={(event) => updateField("password", event.target.value)}
                    placeholder={copy.register.form.passwordPlaceholder}
                    aria-invalid={Boolean(errors.password)}
                  />
                  {errors.password ? <small className="field-error">{errors.password}</small> : null}
                </label>

                <label className="field">
                  <span>{copy.register.form.confirmPassword}</span>
                  <input
                    ref={(node) => {
                      fieldRefs.current.confirmPassword = node;
                    }}
                    type="password"
                    value={form.confirmPassword}
                    onChange={(event) => updateField("confirmPassword", event.target.value)}
                    placeholder={copy.register.form.confirmPasswordPlaceholder}
                    aria-invalid={Boolean(errors.confirmPassword)}
                  />
                  {errors.confirmPassword ? <small className="field-error">{errors.confirmPassword}</small> : null}
                </label>
              </div>

              <label className="checkbox-field">
                <input
                  ref={(node) => {
                    fieldRefs.current.acceptTerms = node;
                  }}
                  type="checkbox"
                  checked={form.acceptTerms}
                  onChange={(event) => updateField("acceptTerms", event.target.checked)}
                />
                <span>{copy.register.form.acceptTerms}</span>
              </label>
              {errors.acceptTerms ? <small className="field-error">{errors.acceptTerms}</small> : null}

              {submitFeedback.message ? (
                <div className={`form-feedback form-feedback--${submitFeedback.tone}`} role="status" aria-live="polite">
                  {submitFeedback.message}
                </div>
              ) : null}

              <div className="modal-card__actions">
                <button className="secondary-button" type="button" onClick={closeRegisterModal}>
                  {copy.register.form.close}
                </button>
                <button className="primary-button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? copy.register.form.submitting : copy.register.form.submit}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
