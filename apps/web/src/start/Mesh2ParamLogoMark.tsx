import type { SVGProps } from "react";

export function Mesh2ParamLogoMark({ title = "", ...props }: SVGProps<SVGSVGElement> & { title?: string }) {
  const titleId = title ? "mesh2param-mark-title" : undefined;
  return (
    <svg viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" strokeLinejoin="round" role={title ? "img" : undefined} aria-labelledby={titleId} aria-hidden={title ? undefined : true} {...props}>
      {title ? <title id={titleId}>{title}</title> : null}
      <path d="M20 2.8 35 11.4v17.2L20 37.2 5 28.6V11.4L20 2.8Z" />
      <path d="m5 11.4 15 8.7 15-8.7M20 20.1v17.1M5 28.6l15-8.5 15 8.5" opacity=".9" />
      <path d="m5 11.4 8.2 4.7L20 2.8m0 17.3-6.8-4v8l6.8 4m0-8 7.4-4.3v8.5L20 28.6" opacity=".7" />
      <path d="m13.2 16.1 6.8 4-6.8 4 6.8 4 7.4-4.3M20 2.8v17.3l7.4 4.2" opacity=".55" />
      <circle cx="20" cy="20.1" r="2.7" fill="var(--color-bg)" />
    </svg>
  );
}

export function MeshTransitionHero() {
  return (
    <svg className="mesh-transition-hero" viewBox="0 0 620 220" role="img" aria-label="A triangulated bracket becoming a clean parametric solid">
      <defs>
        <linearGradient id="mesh-line" x1="0" x2="1"><stop stopColor="#dceaff"/><stop offset="1" stopColor="#6eb1ff"/></linearGradient>
        <radialGradient id="hero-halo"><stop stopColor="#1677de" stopOpacity=".42"/><stop offset="1" stopColor="#1677de" stopOpacity="0"/></radialGradient>
      </defs>
      <ellipse cx="310" cy="112" rx="280" ry="120" fill="url(#hero-halo)"/>
      <g transform="translate(66 25)" fill="none" stroke="url(#mesh-line)" strokeWidth="1.25" strokeLinejoin="round">
        <path d="M35 128 35 57 73 36 145 56 145 128 110 149Z"/>
        <path d="m35 128 74 21 73-42-37-20M35 57l74 22 36-23M109 79v70M145 56l37 21v30"/>
        <path d="m35 57 37 58 37-36 36 48-73-12 73-59-36 93M72 36l37 43-74 49 110-72M35 92l110 35M72 115l73-59" opacity=".55"/>
        <ellipse cx="105" cy="82" rx="17" ry="21" transform="rotate(-20 105 82)"/>
        <ellipse cx="78" cy="125" rx="13" ry="7"/><ellipse cx="128" cy="138" rx="13" ry="7"/>
      </g>
      <g fill="#8cc4ff">
        <circle cx="270" cy="82" r="2"/><circle cx="280" cy="93" r="1.8"/><circle cx="290" cy="104" r="1.6"/><circle cx="300" cy="115" r="1.4"/>
        <circle cx="270" cy="104" r="1.5"/><circle cx="282" cy="115" r="1.3"/><circle cx="294" cy="126" r="1.1"/>
      </g>
      <path d="M302 110h54m-12-10 12 10-12 10" fill="none" stroke="#b9d9ff" strokeWidth="2"/>
      <g transform="translate(380 25)" fill="rgba(77,163,255,.05)" stroke="#e3efff" strokeWidth="1.45" strokeLinejoin="round">
        <path d="M35 128V57l38-21 72 20v71l-36 22Z"/>
        <path d="m35 128 74 21 73-42-37-20M35 57l74 22 36-23M109 79v70M145 56l37 21v30"/>
        <ellipse cx="105" cy="82" rx="17" ry="21" transform="rotate(-20 105 82)" fill="#0a1420"/>
        <ellipse cx="78" cy="125" rx="13" ry="7" fill="#0a1420"/><ellipse cx="128" cy="138" rx="13" ry="7" fill="#0a1420"/>
        <path d="M42 123V64l32-17 62 17v58l-30 17Z" opacity=".45"/>
      </g>
    </svg>
  );
}
