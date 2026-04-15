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
  if (typeof window === "undefined") return "zh-CN";
  const stored = window.localStorage.getItem(siteConfig.localeStorageKey);
  return stored === "zh-CN" || stored === "en-US" ? stored : "zh-CN";
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

function SectionIntro({ eyebrow, title, body, align = "left" }) {
  return (
    <div className={`section-intro reveal section-intro--${align}`}>
      <span className="section-eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      {body ? <p>{body}</p> : null}
    </div>
  );
}

function HeroOrbital({ copy }) {
  return (
    <div className="hero-orbital reveal" aria-label={copy.ariaLabel}>
      <div className="hero-orbital__halo hero-orbital__halo--outer" />
      <div className="hero-orbital__halo hero-orbital__halo--middle" />
      <div className="hero-orbital__halo hero-orbital__halo--inner" />

      <article className="hero-orbital__core">
        <span className="status-pill status-pill--soft">{copy.status}</span>
        <strong>{copy.title}</strong>
        <p>{copy.body}</p>
      </article>

      {copy.cards.map((card, index) => (
        <article
          className={`hero-orbital__card hero-orbital__card--${index + 1}`}
          key={card.title}
        >
          <span>{card.title}</span>
          <p>{card.body}</p>
        </article>
      ))}

      <div className="hero-orbital__tags">
        {copy.tags.map((tag) => (
          <span className="hero-tag" key={tag}>
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}

function WorkspaceStage({ copy }) {
  return (
    <div className="workspace-stage reveal" aria-label={copy.ariaLabel}>
      <div className="workspace-stage__glow" />

      <article className="workspace-frame">
        <div className="workspace-frame__topbar">
          <div className="workspace-brand">
            <img src="/logo-mark.svg" alt="" />
            <div>
              <strong>{copy.windowLabel}</strong>
              <span>{copy.windowMeta}</span>
            </div>
          </div>

          <span className="status-pill">{copy.status}</span>
        </div>

        <div className="workspace-frame__body">
          <aside className="workspace-rail">
            <span className="workspace-label">{copy.railLabel}</span>
            <ul>
              {copy.railItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </aside>

          <div className="workspace-main">
            <div className="workspace-chip-row">
              {copy.chips.map((item) => (
                <span className="workspace-chip" key={item}>
                  {item}
                </span>
              ))}
            </div>

            <div className="workspace-focus">
              <span className="workspace-label">{copy.focusLabel}</span>
              <h3>{copy.focusTitle}</h3>
              <p>{copy.focusBody}</p>
            </div>

            <div className="workspace-panels">
              <article className="workspace-panel">
                <span className="workspace-label">{copy.currentTaskLabel}</span>
                <strong>{copy.currentTask}</strong>
              </article>

              <article className="workspace-panel">
                <span className="workspace-label">{copy.checkpointLabel}</span>
                <strong>{copy.checkpoint}</strong>
              </article>
            </div>

            <div className="workspace-metrics">
              {copy.metrics.map((item) => (
                <div className="workspace-metric" key={item.label}>
                  <strong>{item.value}</strong>
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="workspace-frame__footer">
          <span className="workspace-label">{copy.footerLabel}</span>
          <strong>{copy.footerValue}</strong>
        </div>
      </article>
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

  const copy = siteCopy[locale] || siteCopy["zh-CN"];
  const currentYear = new Date().getFullYear();

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = copy.meta.title;
    window.localStorage.setItem(siteConfig.localeStorageKey, locale);

    const metaDescription = document.querySelector('meta[name="description"]');
    metaDescription?.setAttribute("content", copy.meta.description);
  }, [copy.meta.description, copy.meta.title, locale]);

  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll(".reveal"));
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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
      { threshold: 0.16, rootMargin: "0px 0px -10% 0px" }
    );

    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [locale]);

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
      setSubmitFeedback({ tone: "success", message: response.message });
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
      <div className="site-backdrop site-backdrop--left" />
      <div className="site-backdrop site-backdrop--right" />

      <header className="topbar">
        <a className="brand" href="#top" aria-label={siteConfig.siteName}>
          <img src="/logo-mark.svg" alt="" />
          <div>
            <strong>{siteConfig.siteName}</strong>
            <span>{siteConfig.domain}</span>
          </div>
        </a>

        <nav className="topnav" aria-label="Primary">
          <a href="#capabilities">{copy.nav.capabilities}</a>
          <a href="#experience">{copy.nav.experience}</a>
          <a href="#download">{copy.nav.download}</a>
          <a href="#faq">{copy.nav.faq}</a>
        </nav>

        <div className="topbar-actions">
          <button className="ghost-button" type="button" onClick={toggleLocale}>
            {copy.langSwitch}
          </button>
          <button className="secondary-button" type="button" onClick={openRegisterModal}>
            {copy.nav.register}
          </button>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="hero-copy reveal">
            <span className="announcement-pill">{copy.announcement}</span>
            <span className="hero-eyebrow">{copy.hero.eyebrow}</span>
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

            <div className="hero-mini-meta">
              {copy.hero.labels.map((item) => (
                <span className="hero-mini-pill" key={item}>
                  {item}
                </span>
              ))}
            </div>
          </div>

          <HeroOrbital copy={copy.heroOrbital} />
        </section>

        <section className="content-section" id="capabilities">
          <SectionIntro
            eyebrow={copy.capabilities.eyebrow}
            title={copy.capabilities.title}
            body={copy.capabilities.body}
            align="center"
          />

          <div className="capability-grid">
            {copy.capabilities.items.map((item, index) => (
              <article
                className="capability-card reveal"
                key={item.title}
                style={{ "--delay": `${index * 90}ms` }}
              >
                <span className="capability-note">{item.note}</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="content-section content-section--experience" id="experience">
          <div className="experience-layout">
            <div className="experience-copy reveal">
              <SectionIntro
                eyebrow={copy.experience.eyebrow}
                title={copy.experience.title}
                body={copy.experience.body}
              />

              <ul className="experience-list">
                {copy.experience.bullets.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>

              <div className="experience-signals">
                {copy.experience.signals.map((item) => (
                  <article className="experience-signal" key={item.label}>
                    <strong>{item.value}</strong>
                    <span>{item.label}</span>
                  </article>
                ))}
              </div>
            </div>

            <WorkspaceStage copy={copy.experience.preview} />
          </div>
        </section>

        <section className="content-section content-section--cta" id="download">
          <div className="cta-layout">
            <article className="download-panel reveal">
              <div className="download-panel__header">
                <span className="section-eyebrow">{copy.download.eyebrow}</span>
                <h2>{copy.download.title}</h2>
                <p>{copy.download.body}</p>
              </div>

              <div className="download-meta-grid">
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
                <div>
                  <span>{copy.download.labels.release}</span>
                  <strong>{siteConfig.release.fileName}</strong>
                </div>
              </div>

              <div className="hero-actions">
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

              <ul className="download-notes">
                {copy.download.notes.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>

            <article className="register-panel reveal">
              <span className="section-eyebrow">{copy.register.eyebrow}</span>
              <h2>{copy.register.title}</h2>
              <p>{copy.register.body}</p>

              <div className="register-benefits">
                {copy.register.benefits.map((item) => (
                  <div className="register-benefit" key={item}>
                    {item}
                  </div>
                ))}
              </div>

              <button className="primary-button" type="button" onClick={openRegisterModal}>
                {copy.register.cta}
              </button>
            </article>
          </div>
        </section>

        <section className="content-section content-section--faq" id="faq">
          <SectionIntro
            eyebrow={copy.faq.eyebrow}
            title={copy.faq.title}
            body={copy.faq.body}
            align="center"
          />

          <div className="faq-list">
            {copy.faq.items.map((item, index) => (
              <details
                className="faq-item reveal"
                key={item.question}
                style={{ "--delay": `${index * 70}ms` }}
              >
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
        <div
          className="modal-shell"
          onMouseDown={(event) => event.target === event.currentTarget && closeRegisterModal()}
        >
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
              <button
                className="icon-button"
                type="button"
                onClick={closeRegisterModal}
                aria-label={copy.register.form.close}
              >
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
                  {errors.confirmPassword ? (
                    <small className="field-error">{errors.confirmPassword}</small>
                  ) : null}
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
