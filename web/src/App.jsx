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

function SectionHeader({ eyebrow, title, body, align = "left" }) {
  return (
    <div className={`section-header reveal section-header--${align}`}>
      <span className="section-header__eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      {body ? <p>{body}</p> : null}
    </div>
  );
}

function HeroStage({ copy }) {
  return (
    <div className="hero-stage reveal" aria-label={copy.ariaLabel}>
      <div className="hero-stage__ambient hero-stage__ambient--one" />
      <div className="hero-stage__ambient hero-stage__ambient--two" />
      <div className="hero-stage__orbit hero-stage__orbit--one" />
      <div className="hero-stage__orbit hero-stage__orbit--two" />

      <article className="hero-stage__window">
        <div className="hero-stage__window-bar">
          <div className="hero-stage__window-brand">
            <img src="/aoryn-logo-web.png" alt="" />
            <div>
              <strong>{copy.windowLabel}</strong>
              <span>{copy.modeLabel}</span>
            </div>
          </div>

          <span className="stage-pill">{copy.status}</span>
        </div>

        <div className="hero-stage__window-body">
          <aside className="hero-stage__sidebar">
            <span className="stage-label">{copy.sideTitle}</span>
            <ul>
              {copy.sideItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </aside>

          <div className="hero-stage__main">
            <article className="hero-stage__focus">
              <span className="stage-label">{copy.focusLabel}</span>
              <h3>{copy.focusTitle}</h3>
              <p>{copy.focusBody}</p>
            </article>

            <div className="hero-stage__lane-grid">
              {copy.lanes.map((item) => (
                <article className="hero-stage__lane" key={item.title}>
                  <span>{item.title}</span>
                  <p>{item.body}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </article>

      {copy.floatCards.map((item, index) => (
        <article
          className={`hero-stage__float hero-stage__float--${index + 1}`}
          key={item.title}
        >
          <span>{item.eyebrow}</span>
          <strong>{item.title}</strong>
          <p>{item.body}</p>
        </article>
      ))}
    </div>
  );
}

function ExperienceShowcase({ copy }) {
  return (
    <div className="showcase reveal" aria-label={copy.ariaLabel}>
      <div className="showcase__mist" />

      <article className="showcase__frame">
        <div className="showcase__bar">
          <strong>{copy.windowLabel}</strong>
          <span className="stage-pill stage-pill--soft">{copy.status}</span>
        </div>

        <div className="showcase__body">
          <div className="showcase__rail">
            <span className="stage-label">{copy.railLabel}</span>
            <ul>
              {copy.railItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>

          <div className="showcase__canvas">
            <article className="showcase__focus">
              <span className="stage-label">{copy.panelLabel}</span>
              <h3>{copy.panelTitle}</h3>
              <p>{copy.panelBody}</p>
            </article>

            <div className="showcase__cards">
              {copy.cards.map((item) => (
                <article className="showcase__card" key={item.title}>
                  <span>{item.title}</span>
                  <strong>{item.value}</strong>
                </article>
              ))}
            </div>
          </div>
        </div>

        <div className="showcase__footer">
          <span className="stage-label">{copy.footerLabel}</span>
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
  const downloadFacts = [
    { label: copy.download.labels.version, value: siteConfig.release.version },
    { label: copy.download.labels.platform, value: siteConfig.release.platform },
    { label: copy.download.labels.size, value: siteConfig.release.fileSize },
  ];

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
      { threshold: 0.18, rootMargin: "0px 0px -8% 0px" }
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
      <div className="site-shell__aura site-shell__aura--left" />
      <div className="site-shell__aura site-shell__aura--right" />

      <header className="topbar">
        <a className="brand" href="#top" aria-label={siteConfig.siteName}>
          <img src="/aoryn-logo-web.png" alt="" />
          <strong>{siteConfig.siteName}</strong>
        </a>

        <nav className="topnav" aria-label="Primary">
          <a href="#capabilities">{copy.nav.capabilities}</a>
          <a href="#experience">{copy.nav.experience}</a>
          <a href="#download">{copy.nav.download}</a>
        </nav>

        <div className="topbar-actions">
          <button className="ghost-button" type="button" onClick={toggleLocale}>
            {copy.langSwitch}
          </button>
          <button className="topbar-register" type="button" onClick={openRegisterModal}>
            {copy.nav.register}
          </button>
        </div>
      </header>

      <main id="top">
        <section className="hero">
          <div className="hero-copy reveal">
            <span className="hero-copy__eyebrow">{copy.hero.eyebrow}</span>
            <h1>{copy.hero.title}</h1>
            <p className="hero-copy__body">{copy.hero.body}</p>

            <div className="hero-copy__actions">
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
          </div>

          <HeroStage copy={copy.heroStage} />
        </section>

        <section className="section" id="capabilities">
          <SectionHeader
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
                style={{ "--delay": `${index * 80}ms` }}
              >
                <span>{item.note}</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="section section--experience" id="experience">
          <div className="experience-layout">
            <div className="experience-copy reveal">
              <SectionHeader
                eyebrow={copy.experience.eyebrow}
                title={copy.experience.title}
                body={copy.experience.body}
              />

              <ul className="experience-points">
                {copy.experience.points.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>

            <ExperienceShowcase copy={copy.experience.stage} />
          </div>
        </section>

        <section className="section section--cta" id="download">
          <div className="cta-layout">
            <article className="download-card reveal">
              <span className="section-header__eyebrow">{copy.download.eyebrow}</span>
              <h2>{copy.download.title}</h2>
              <p>{copy.download.body}</p>

              <div className="download-card__facts">
                {downloadFacts.map((item) => (
                  <div key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>

              <div className="hero-copy__actions">
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

              <p className="download-card__caption">
                {siteConfig.release.fileName} · {siteConfig.release.hosting}
              </p>
            </article>

            <article className="register-card reveal">
              <span className="section-header__eyebrow">{copy.register.eyebrow}</span>
              <h2>{copy.register.title}</h2>
              <p>{copy.register.body}</p>

              <div className="register-card__items">
                {copy.register.items.map((item) => (
                  <div className="register-card__item" key={item}>
                    {item}
                  </div>
                ))}
              </div>

              <button className="secondary-button secondary-button--wide" type="button" onClick={openRegisterModal}>
                {copy.register.cta}
              </button>
            </article>
          </div>
        </section>

        <section className="section section--faq" id="faq">
          <div className="faq-shell reveal">
            <SectionHeader
              eyebrow={copy.faq.eyebrow}
              title={copy.faq.title}
              body={copy.faq.body}
            />

            <div className="faq-list">
              {copy.faq.items.map((item) => (
                <details className="faq-item" key={item.question}>
                  <summary>{item.question}</summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="site-footer__brand">
          <img src="/aoryn-logo-web.png" alt="" />
          <div>
            <strong>{siteConfig.siteName}</strong>
            <p>{copy.footer.tagline}</p>
          </div>
        </div>
        <p className="site-footer__meta">
          Copyright {currentYear} {copy.footer.copyright}
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
                <span className="section-header__eyebrow">{copy.register.eyebrow}</span>
                <h2 id="register-modal-title">{copy.register.modalTitle}</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                onClick={closeRegisterModal}
                aria-label={copy.register.form.close}
              >
                x
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
