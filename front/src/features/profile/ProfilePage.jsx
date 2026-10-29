import { useNavigate } from "react-router-dom";
import { AppShell } from "../../layout/AppShell.jsx";
import { Page, PageHeader } from "../../layout/Page.jsx";
import { ProfileForm } from "./ProfileForm.jsx";

export function ProfilePage() {
  const navigate = useNavigate();

  return (
    <AppShell nav={{ active: "profile", mobile: "back", title: "Profile", back: "/settings", tabs: false }} scroll>
      <Page>
        <PageHeader title="Profile" hideTitleOnMobile
          subtitle="This information is added to the context of every answer."
          mobileSubtitle="Added to the context of every answer." />
        <ProfileForm onCancel={() => navigate("/chat")} />
      </Page>
    </AppShell>
  );
}
