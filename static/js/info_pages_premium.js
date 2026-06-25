(function () {
  const ready = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  };

  ready(() => {
    const revealTargets = document.querySelectorAll(".si-reveal");
    if (revealTargets.length) {
      const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("si-visible");
          revealObserver.unobserve(entry.target);
        });
      }, { rootMargin: "0px 0px -30px 0px", threshold: 0.08 });

      revealTargets.forEach((target) => revealObserver.observe(target));
    }

    const links = Array.from(document.querySelectorAll(".legal-toc a[href^='#']"));
    const sections = links
      .map((link) => document.querySelector(link.getAttribute("href")))
      .filter(Boolean);

    if (!links.length || !sections.length) return;

    const setActive = (id) => {
      links.forEach((link) => {
        link.classList.toggle("is-active", link.getAttribute("href") === `#${id}`);
      });
    };

    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

      if (visible && visible.target.id) {
        setActive(visible.target.id);
      }
    }, {
      rootMargin: "-18% 0px -64% 0px",
      threshold: [0.1, 0.25, 0.5],
    });

    sections.forEach((section) => observer.observe(section));
    if (sections[0] && sections[0].id) setActive(sections[0].id);
  });
})();
