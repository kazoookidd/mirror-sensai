import { useNavigate } from "react-router-dom";
import { TestTag } from "../../components/feedback/TestTag/TestTag.jsx";
import { AppShell } from "../../layout/AppShell.jsx";
import { Page, PageHeader } from "../../layout/Page.jsx";
import { ProfileForm } from "./ProfileForm.jsx";

export function ProfilePage() {
  const navigate = useNavigate();

  return (
    <AppShell nav={{ active: "profile", mobile: "back", title: "Profile", back: "/settings", tabs: false }} scroll>
      <Page>
        <PageHeader title="Profile" hideTitleOnMobile titleExtra={<TestTag />}
          subtitle="This information is added to the context of every new chat."
          mobileSubtitle="Added to the context of every new chat." />
        <ProfileForm onCancel={() => navigate("/chat")} />
      </Page>
    </AppShell>
  );
}
