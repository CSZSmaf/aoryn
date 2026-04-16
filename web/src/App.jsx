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
import { submitRegistration } from "./lib/submitRegistration";

const INITIAL_FORM = {
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
};

function getPreferredLocale() {
  if (typeof window === "undefined") return "zh-CN";
  const stored = window.localStorage.getItem(siteConfig.localeStorageKey);
  return stored === "zh-CN" || stored === "en-US" ? stored : "zh-CN";
}

function getPageKey(pathname) {
  return ROUTE_TO_PAGE_KEY[pathname] || "home";
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

function SectionHeading({ eyebrow, title, body, align = "left" }) {
  return (
    <div className={`section-heading section-heading--${align} reveal`}>
      <span className="section-heading__eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      {body ? <p>{body}</p> : null}
    </div>
  );
}

function PageHero({ copy, children }) {
  return (
    <section className="detail-hero reveal">
      <div className="detail-hero__copy">
        <span className="section-heading__eyebrow">{copy.eyebrow}</span>
        <h1>{copy.title}</h1>
        <p>{copy.body}</p>
      </div>
      {children ? <div className="detail-hero__aside">{children}</div> : null}
    </section>
  );
}

function HeroStage({ copy }) {
  return (
    <div className="hero-stage reveal" aria-label={copy.ariaLabel}>
      <div className="hero-stage__glow hero-stage__glow--left" />
      <div className="hero-stage__glow hero-stage__glow--right" />

      <article className="hero-stage__window">
        <div className="hero-stage__topbar">
          <div className="hero-stage__brand">
            <img src="/aoryn-logo-web.png" alt="" />
            <div>
              <strong>{copy.windowLabel}</strong>
              <span>{copy.windowMeta}</span>
            </div>
          </div>
          <span className="status-pill">{copy.status}</span>
        </div>

        <div className="hero-stage__body">
          <aside className="hero-stage__rail">
            <span>{copy.railLabel}</span>
            <ul>
              {copy.railItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </aside>

          <div className="hero-stage__content">
            <div className="chip-row">
              {copy.chips.map((item) => (
                <span className="chip" key={item}>
                  {item}
                </span>
              ))}
            </div>

            <div className="hero-stage__focus">
              <span>{copy.focusLabel}</span>
              <strong>{copy.focusTitle}</strong>
              <p>{copy.focusBody}</p>
            </div>

            <div className="metric-row">
              {copy.metrics.map((item) => (
                <div className="metric-card" key={item.label}>
                  <strong>{item.value}</strong>
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </article>

      {copy.floatingCards.map((item, index) => (
        <article className={`floating-card floating-card--${index + 1}`} key={item.title}>
          <span>{item.eyebrow}</span>
          <strong>{item.title}</strong>
        </article>
      ))}
    </div>
  );
}

function WorkspacePreview({ copy }) {
  return (
    <div className="workspace-preview reveal" aria-label={copy.ariaLabel}>
      <div className="workspace-preview__plane workspace-preview__plane--outer" />
      <div className="workspace-preview__plane workspace-preview__plane--inner" />

      <article className="workspace-window">
        <div className="workspace-window__topbar">
          <div className="hero-stage__brand">
            <img src="/aoryn-logo-web.png" alt="" />
            <div>
              <strong>{copy.windowLabel}</strong>
              <span>{copy.windowMeta}</span>
            </div>
          </div>
          <span className="status-pill status-pill--soft">{copy.status}</span>
        </div>

        <div className="workspace-window__body">
          <aside className="workspace-window__rail">
            <span>{copy.railLabel}</span>
            <ul>
              {copy.railItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </aside>

          <div className="workspace-window__main">
            <div className="chip-row">
              {copy.chips.map((item) => (
                <span className="chip chip--light" key={item}>
                  {item}
                </span>
              ))}
            </div>

            <div className="workspace-window__focus">
              <span>{copy.focusLabel}</span>
              <h3>{copy.focusTitle}</h3>
              <p>{copy.focusBody}</p>
            </div>

            <div className="workspace-window__cards">
              {copy.cards.map((item) => (
                <article className="workspace-mini-card" key={item.title}>
                  <span>{item.title}</span>
                  <strong>{item.value}</strong>
                </article>
              ))}
            </div>

            <div className="metric-row metric-row--wide">
              {copy.metrics.map((item) => (
                <div className="metric-card metric-card--soft" key={item.label}>
                  <strong>{item.value}</strong>
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="workspace-window__footer">
          <span>{copy.footerLabel}</span>
          <strong>{copy.footerValue}</strong>
        </div>
      </article>
    </div>
  );
}

function HomePage({ copy, openRegisterModal }) {
  const pageCopy = copy.pages.home;

  return (
    <>
      <section className="home-hero">
        <div className="home-hero__copy reveal">
          <span className="home-hero__eyebrow">{pageCopy.hero.eyebrow}</span>
          <h1 className="home-hero__title">
            {pageCopy.hero.titleLines.map((line) => (
              <span key={line}>{line}</span>
            ))}
          </h1>
          <p className="home-hero__body">{pageCopy.hero.body}</p>

          <div className="button-row">
            <a
              className="primary-button"
              href={siteConfig.release.downloadUrl}
              target="_blank"
              rel="noreferrer"
            >
              {pageCopy.hero.primaryCta}
            </a>
            <button className="secondary-button" type="button" onClick={openRegisterModal}>
              {pageCopy.hero.secondaryCta}
            </button>
          </div>
        </div>

        <HeroStage copy={pageCopy.stage} />
      </section>

      <section className="section-shell section-shell--compact">
        <SectionHeading
          eyebrow={pageCopy.capabilities.eyebrow}
          title={pageCopy.capabilities.title}
          body={pageCopy.capabilities.body}
        />

        <div className="capability-grid">
          {pageCopy.capabilities.items.map((item) => (
            <Link className="capability-card reveal" key={item.title} to={item.href}>
              <span className="capability-card__note">{item.note}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
              <strong>{item.linkLabel}</strong>
            </Link>
          ))}
        </div>
      </section>

      <section className="section-shell">
        <div className="spotlight-layout">
          <div className="spotlight-copy reveal">
            <SectionHeading
              eyebrow={pageCopy.spotlight.eyebrow}
              title={pageCopy.spotlight.title}
              body={pageCopy.spotlight.body}
            />

            <div className="button-row button-row--inline">
              <Link className="secondary-button" to="/workspace">
                {pageCopy.spotlight.primaryCta}
              </Link>
              <Link className="text-link" to="/product">
                {pageCopy.spotlight.secondaryCta}
              </Link>
            </div>
          </div>

          <WorkspacePreview copy={pageCopy.spotlight.preview} />
        </div>
      </section>

      <section className="section-shell">
        <article className="download-band reveal">
          <div>
            <span className="section-heading__eyebrow">{pageCopy.cta.eyebrow}</span>
            <h2>{pageCopy.cta.title}</h2>
            <p>{pageCopy.cta.body}</p>
          </div>

          <div className="button-row">
            <a
              className="primary-button"
              href={siteConfig.release.downloadUrl}
              target="_blank"
              rel="noreferrer"
            >
              {pageCopy.cta.primaryCta}
            </a>
            <button className="secondary-button" type="button" onClick={openRegisterModal}>
              {pageCopy.cta.secondaryCta}
            </button>
          </div>
        </article>
      </section>
    </>
  );
}

function ProductPage({ copy }) {
  const pageCopy = copy.pages.product;

  return (
    <>
      <PageHero copy={pageCopy.hero}>
        <div className="hero-stat-stack">
          {pageCopy.hero.stats.map((item) => (
            <article className="hero-stat-card" key={item.label}>
              <strong>{item.value}</strong>
              <span>{item.label}</span>
            </article>
          ))}
        </div>
      </PageHero>

      <section className="section-shell">
        <SectionHeading
          eyebrow={pageCopy.pillars.eyebrow}
          title={pageCopy.pillars.title}
          body={pageCopy.pillars.body}
        />

        <div className="detail-grid detail-grid--three">
          {pageCopy.pillars.items.map((item) => (
            <article className="detail-card reveal" key={item.title}>
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

        <div className="detail-grid">
          {pageCopy.workflow.items.map((item) => (
            <article className="detail-card detail-card--step reveal" key={item.title}>
              <span className="detail-card__eyebrow">{item.step}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-shell">
        <article className="insight-panel reveal">
          <div className="insight-panel__copy">
            <span className="section-heading__eyebrow">{pageCopy.evidence.eyebrow}</span>
            <h2>{pageCopy.evidence.title}</h2>
            <p>{pageCopy.evidence.body}</p>
          </div>

          <div className="metric-row metric-row--wide">
            {pageCopy.evidence.metrics.map((item) => (
              <div className="metric-card metric-card--soft" key={item.label}>
                <strong>{item.value}</strong>
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </article>
      </section>
    </>
  );
}

function WorkspacePage({ copy }) {
  const pageCopy = copy.pages.workspace;

  return (
    <>
      <PageHero copy={pageCopy.hero}>
        <div className="hero-stat-stack">
          {pageCopy.hero.stats.map((item) => (
            <article className="hero-stat-card" key={item.label}>
              <strong>{item.value}</strong>
              <span>{item.label}</span>
            </article>
          ))}
        </div>
      </PageHero>

      <section className="section-shell">
        <WorkspacePreview copy={pageCopy.preview} />
      </section>

      <section className="section-shell">
        <SectionHeading
          eyebrow={pageCopy.modules.eyebrow}
          title={pageCopy.modules.title}
          body={pageCopy.modules.body}
        />

        <div className="detail-grid detail-grid--three">
          {pageCopy.modules.items.map((item) => (
            <article className="detail-card reveal" key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-shell">
        <SectionHeading
          eyebrow={pageCopy.timeline.eyebrow}
          title={pageCopy.timeline.title}
          body={pageCopy.timeline.body}
        />

        <div className="timeline-grid">
          {pageCopy.timeline.items.map((item) => (
            <article className="timeline-card reveal" key={item.title}>
              <span>{item.step}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function DownloadPage({ copy, openRegisterModal }) {
  const pageCopy = copy.pages.download;

  return (
    <>
      <PageHero copy={pageCopy.hero}>
        <div className="button-row button-row--stacked">
          <a
            className="primary-button"
            href={siteConfig.release.downloadUrl}
            target="_blank"
            rel="noreferrer"
          >
            {pageCopy.hero.primaryCta}
          </a>
          <button className="secondary-button" type="button" onClick={openRegisterModal}>
            {pageCopy.hero.secondaryCta}
          </button>
        </div>
      </PageHero>

      <section className="section-shell">
        <div className="download-meta-grid">
          {pageCopy.metaGrid.map((item) => (
            <article className="download-meta-card reveal" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </article>
          ))}
        </div>
      </section>

      <section className="section-shell">
        <SectionHeading
          eyebrow={pageCopy.steps.eyebrow}
          title={pageCopy.steps.title}
          body={pageCopy.steps.body}
        />

        <div className="detail-grid detail-grid--three">
          {pageCopy.steps.items.map((item) => (
            <article className="detail-card detail-card--step reveal" key={item.title}>
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
          {pageCopy.faq.items.map((item) => (
            <details className="faq-item reveal" key={item.question}>
              <summary>{item.question}</summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}

function RegisterModal({
  copy,
  form,
  errors,
  isSubmitting,
  submitFeedback,
  closeRegisterModal,
  handleSubmit,
  updateField,
  modalRef,
  firstInputRef,
  fieldRefs,
}) {
  return (
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
            <span className="section-heading__eyebrow">{copy.register.eyebrow}</span>
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

        <div className="register-benefits">
          {copy.register.benefits.map((item) => (
            <div className="register-benefit" key={item}>
              {item}
            </div>
          ))}
        </div>

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
  );
}

function AppFrame() {
  const [locale, setLocale] = useState(getPreferredLocale);
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitFeedback, setSubmitFeedback] = useState({ tone: "", message: "" });

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
      { threshold: 0.16, rootMargin: "0px 0px -8% 0px" }
    );

    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [locale, location.pathname]);

  useEffect(() => {
    if (isRegisterOpen) return;
    const previous = lastActiveElementRef.current;
    if (previous && typeof previous.focus === "function") {
      window.requestAnimationFrame(() => previous.focus());
    }
  }, [isRegisterOpen]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    if (isRegisterOpen || isMenuOpen) {
      document.body.style.overflow = "hidden";
    }

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        if (isRegisterOpen) {
          setIsRegisterOpen(false);
        } else if (isMenuOpen) {
          setIsMenuOpen(false);
        }
      } else if (isRegisterOpen) {
        trapFocus(modalRef.current, event);
      }
    };

    if (isRegisterOpen || isMenuOpen) {
      window.addEventListener("keydown", handleKeyDown);
    }

    if (isRegisterOpen) {
      window.requestAnimationFrame(() => {
        firstInputRef.current?.focus();
      });
    }

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMenuOpen, isRegisterOpen]);

  const toggleLocale = () => {
    setLocale((current) => (current === "zh-CN" ? "en-US" : "zh-CN"));
  };

  const openRegisterModal = (event) => {
    lastActiveElementRef.current = event?.currentTarget || document.activeElement;
    setForm(INITIAL_FORM);
    setErrors({});
    setSubmitFeedback({ tone: "", message: "" });
    setIsMenuOpen(false);
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
          displayName: form.name.trim(),
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

  const navItems = [
    { to: "/product", label: copy.nav.product },
    { to: "/workspace", label: copy.nav.workspace },
    { to: "/download", label: copy.nav.download },
  ];

  return (
    <div className="site-shell">
      <div className="site-shell__glow site-shell__glow--left" />
      <div className="site-shell__glow site-shell__glow--right" />

      <header className="topbar">
        <Link className="brand" to="/" aria-label={siteConfig.siteName}>
          <img src="/aoryn-logo-web.png" alt="" />
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
          <button className="secondary-button secondary-button--nav" type="button" onClick={openRegisterModal}>
            {copy.nav.register}
          </button>
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
        <div
          className="mobile-menu-shell"
          onMouseDown={(event) => event.target === event.currentTarget && setIsMenuOpen(false)}
        >
          <div className="mobile-menu">
            <div className="mobile-menu__head">
              <strong>{siteConfig.siteName}</strong>
              <button className="icon-button" type="button" onClick={() => setIsMenuOpen(false)}>
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
            </div>

            <div className="mobile-menu__actions">
              <button className="ghost-button" type="button" onClick={toggleLocale}>
                {copy.langSwitch}
              </button>
              <button className="primary-button" type="button" onClick={openRegisterModal}>
                {copy.nav.register}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <main className="page-root">
        <Routes>
          <Route path="/" element={<HomePage copy={copy} openRegisterModal={openRegisterModal} />} />
          <Route path="/product" element={<ProductPage copy={copy} />} />
          <Route path="/workspace" element={<WorkspacePage copy={copy} />} />
          <Route
            path="/download"
            element={<DownloadPage copy={copy} openRegisterModal={openRegisterModal} />}
          />
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
        </div>

        <p className="site-footer__copyright">
          © {currentYear} {copy.footer.copyright}
        </p>
      </footer>

      {isRegisterOpen ? (
        <RegisterModal
          copy={copy}
          form={form}
          errors={errors}
          isSubmitting={isSubmitting}
          submitFeedback={submitFeedback}
          closeRegisterModal={closeRegisterModal}
          handleSubmit={handleSubmit}
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
