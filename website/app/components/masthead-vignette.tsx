import { withBasePath } from "@/app/lib/base-path";

// The chosen production artwork is fixed. Historical candidates live outside
// this website; query parameters cannot change the published masthead.
export function MastheadVignette() {
  return (
    <span
      className="masthead-vignette"
      data-vignette="contour"
      aria-hidden="true"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={withBasePath("/artwork/vignettes/contour.png")}
        alt=""
        width="337"
        height="145"
        decoding="async"
      />
    </span>
  );
}
