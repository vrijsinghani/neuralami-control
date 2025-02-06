import { ProjectMember, ProjectData } from '../types';

// @mui material components
import Tooltip from "@mui/material/Tooltip";
import SoftBox from "../../../../../components/SoftBox";
import SoftTypography from "../../../../../components/SoftTypography";
import SoftAvatar from "../../../../../components/SoftAvatar";
import SoftProgress from "../../../../../components/SoftProgress";

// Images
import logoXD from "@images/small-logos/logo-xd.svg";
import logoAtlassian from "@images/small-logos/logo-atlassian.svg";
import logoSlack from "@images/small-logos/logo-slack.svg";
import logoSpotify from "@images/small-logos/logo-spotify.svg";
import logoJira from "@images/small-logos/logo-jira.svg";
import logoInvesion from "@images/small-logos/logo-invision.svg";
import team1 from "@images/team-1.jpg";
import team2 from "@images/team-2.jpg";
import team3 from "@images/team-3.jpg";
import team4 from "@images/team-4.jpg";

interface AvatarGroupProps {
  src: string;
  name: string;
}

export const projectsData = (): ProjectData => {
  const avatars = (members: AvatarGroupProps[]) =>
    members.map(({ src, name }) => (
      <Tooltip key={name} title={name} placement="bottom">
        <SoftAvatar
          src={src}
          alt="name"
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
    ));

  return {
    columns: [
      { name: "companies", align: "left" },
      { name: "members", align: "left" },
      { name: "budget", align: "center" },
      { name: "completion", align: "center" },
    ],

    rows: [
      {
        companies: {
          logo: logoXD,
          name: "Soft UI XD Version"
        },
        members: (
          <SoftBox display="flex" py={1}>
            {avatars([
              { src: team1, name: "Ryan Tompson" },
              { src: team2, name: "Romina Hadid" },
              { src: team3, name: "Alexander Smith" },
              { src: team4, name: "Jessica Doe" },
            ])}
          </SoftBox>
        ),
        budget: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $14,000
          </SoftTypography>
        ),
        completion: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={60} color="info" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        companies: {
          logo: logoAtlassian,
          name: "Add Progress Track"
        },
        members: (
          <SoftBox display="flex" py={1}>
            {avatars([
              { src: team2, name: "Romina Hadid" },
              { src: team4, name: "Jessica Doe" },
            ])}
          </SoftBox>
        ),
        budget: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $3,000
          </SoftTypography>
        ),
        completion: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={10} color="info" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        companies: {
          logo: logoSlack,
          name: "Fix Platform Errors"
        },
        members: (
          <SoftBox display="flex" py={1}>
            {avatars([
              { src: team1, name: "Ryan Tompson" },
              { src: team3, name: "Alexander Smith" },
            ])}
          </SoftBox>
        ),
        budget: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            Not set
          </SoftTypography>
        ),
        completion: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={100} color="success" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        companies: {
          logo: logoSpotify,
          name: "Launch our Mobile App"
        },
        members: (
          <SoftBox display="flex" py={1}>
            {avatars([
              { src: team4, name: "Jessica Doe" },
              { src: team3, name: "Alexander Smith" },
              { src: team2, name: "Romina Hadid" },
              { src: team1, name: "Ryan Tompson" },
            ])}
          </SoftBox>
        ),
        budget: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $20,500
          </SoftTypography>
        ),
        completion: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={100} color="success" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        companies: {
          logo: logoJira,
          name: "Add the New Pricing Page"
        },
        members: (
          <SoftBox display="flex" py={1}>
            {avatars([{ src: team4, name: "Jessica Doe" }])}
          </SoftBox>
        ),
        budget: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $500
          </SoftTypography>
        ),
        completion: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={25} color="info" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        companies: {
          logo: logoInvesion,
          name: "Redesign New Online Shop"
        },
        members: (
          <SoftBox display="flex" py={1}>
            {avatars([
              { src: team1, name: "Ryan Tompson" },
              { src: team4, name: "Jessica Doe" },
            ])}
          </SoftBox>
        ),
        budget: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $2,000
          </SoftTypography>
        ),
        completion: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={40} color="info" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
    ],
  };
}; 