import { FC } from 'react';
import Tooltip from "@mui/material/Tooltip";
import SoftBox from "../../../../components/SoftBox";
import SoftTypography from "../../../../components/SoftTypography";
import SoftAvatar from "../../../../components/SoftAvatar";
import SoftProgress from "../../../../components/SoftProgress";
import { projectsData } from "./data";
import { ProjectMember } from "./types";

const Projects: FC = () => {
  const { columns, rows } = projectsData();

  const renderMembers = (members: ProjectMember[]) => (
    <SoftBox display="flex" py={1}>
      {members.map(({ src, name }) => (
        <Tooltip key={name} title={name} placement="bottom">
          <SoftAvatar
            src={src}
            alt={name}
            size="xs"
            sx={{
              border: ({ borders: { borderWidth }, palette: { white } }) =>
                `${borderWidth[2]} solid ${white.main}`,
              cursor: "pointer",
              position: "relative",
              ml: -1.25,
              "&:hover, &:focus": {
                zIndex: "10",
              },
            }}
          />
        </Tooltip>
      ))}
    </SoftBox>
  );

  return (
    <SoftBox>
      {rows.map((row, index) => (
        <SoftBox key={index} display="flex" justifyContent="space-between" alignItems="center" p={3}>
          <SoftBox display="flex" alignItems="center">
            <SoftBox mr={2}>
              <SoftAvatar src={row.companies.logo} alt={row.companies.name} variant="square" size="sm" />
            </SoftBox>
            <SoftBox display="flex" flexDirection="column">
              <SoftTypography variant="button" fontWeight="medium">
                {row.companies.name}
              </SoftTypography>
            </SoftBox>
          </SoftBox>
          {renderMembers(row.members)}
          <SoftBox>
            <SoftTypography variant="caption" color="text" fontWeight="medium">
              {row.budget}
            </SoftTypography>
          </SoftBox>
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={row.completion} color="info" variant="gradient" label={false} />
          </SoftBox>
        </SoftBox>
      ))}
    </SoftBox>
  );
};

export default Projects; 