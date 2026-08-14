import Link from "next/link";

export default function NotFound() {
  return (
    <main className="state-page">
      <section className="state-card">
        <span className="state-card__code">404</span>
        <h1>That workspace view does not exist</h1>
        <p>Return to the approved live cohort explorer.</p>
        <Link className="ui-button ui-button--secondary ui-button--medium" href="/">
          Return to overview
        </Link>
      </section>
    </main>
  );
}
