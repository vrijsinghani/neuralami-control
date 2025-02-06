export interface ProjectMember {
  src: string;
  name: string;
}

export interface ProjectCompany {
  logo: string;
  name: string;
}

export interface ProjectRow {
  companies: ProjectCompany;
  members: ProjectMember[];
  budget: string;
  completion: number;
}

export interface ProjectColumn {
  name: string;
  align: 'left' | 'right' | 'center';
}

export interface ProjectData {
  columns: ProjectColumn[];
  rows: ProjectRow[];
} 