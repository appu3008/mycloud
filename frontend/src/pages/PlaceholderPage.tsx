import { PageTitle } from "../components/Layout";

/**
 * Honest placeholder: pages that arrive in later phases render real, labeled
 * stubs — no fake data, no pretend functionality (rule 11 / rule 22).
 */
export function PlaceholderPage() {
  return (
    <div>
      <PageTitle title="Coming up" />
      <div className="empty-cell">
        This feature ships in a later phase of the build plan; the sidebar stays
        honest about it rather than showing placeholder content.
      </div>
    </div>
  );
}
