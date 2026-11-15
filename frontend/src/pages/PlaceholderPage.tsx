import { PageTitle, PageTagline } from "../components/Layout";

/**
 * Honest placeholder for pages that ship in later phases — labeled as such,
 * no fake data, no pretend functionality (spec rules 11 / 22).
 */
export function PlaceholderPage() {
  return (
    <div>
      <PageTitle title="Coming up" />
      <div className="placeholder-body card">
        <p className="mono-label">Not built yet</p>
        <p>
          This feature ships in a later phase of the build plan. The navigation
          stays honest about it rather than showing placeholder content.
        </p>
      </div>
      <PageTagline>Built in order. Nothing faked.</PageTagline>
    </div>
  );
}
