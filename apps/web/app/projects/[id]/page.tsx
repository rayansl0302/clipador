import { ProjectEditor } from "@/components/project-editor";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function ProjectPage({ params }: PageProps) {
  const { id } = await params;
  return <ProjectEditor projectId={id} />;
}
