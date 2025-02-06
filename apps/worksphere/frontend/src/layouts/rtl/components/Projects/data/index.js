// @mui material components
import Tooltip from "@mui/material/Tooltip";

// Soft UI Dashboard React components
import SoftBox from "../../../../../components/SoftBox";
import SoftTypography from "../../../../../components/SoftBox";
import SoftAvatar from "../../../../../components/SoftBox";
import SoftProgress from "../../../../../components/SoftBox";

// Images
import logoXD from "../../../../../components/SoftBox";
import logoAtlassian from "../../../../../components/SoftBox";
import logoSlack from "../../../../../components/SoftBox";
import logoSpotify from "../../../../../components/SoftBox";
import logoJira from "../../../../../components/SoftBox";
import logoInvesion from "../../../../../components/SoftBox";
import team1 from "../../../../../components/SoftBox";
import team2 from "../../../../../components/SoftBox";
import team3 from "../../../../../components/SoftBox";
import team4 from "../../../../../components/SoftBox";

export default function data() {
  const avatars = (members) =>
    members.map(([image, name]) => (
      <Tooltip key={name} title={name} placeholder="bottom">
        <SoftAvatar
          src={image}
          alt="name"
          size="xs"
          sx={{
            border: ({ borders: { borderWidth }, palette: { white } }) =>
              `${borderWidth[2]} solid ${white.main}`,
            cursor: "pointer",
            position: "relative",

            "&:not(:first-of-type)": {
              ml: -1.25,
            },

            "&:hover, &:focus": {
              zIndex: "10",
            },
          }}
        />
      </Tooltip>
    ));

  return {
    columns: [
      { name: "المشروع", align: "left" },
      { name: "أعضاء", align: "left" },
      { name: "ميزانية", align: "center" },
      { name: "إكمال", align: "center" },
    ],

    rows: [
      {
        المشروع: [logoXD, "Soft UI XD الإصدار"],
        أعضاء: (
          <SoftBox display="flex" py={1}>
            {avatars([
              [team1, "Ryan Tompson"],
              [team2, "Romina Hadid"],
              [team3, "Alexander Smith"],
              [team4, "Jessica Doe"],
            ])}
          </SoftBox>
        ),
        ميزانية: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $14,000
          </SoftTypography>
        ),
        إكمال: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={60} color="info" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        المشروع: [logoAtlassian, "أضف مسار التقدم إلى التطبيق الداخلي"],
        أعضاء: (
          <SoftBox display="flex" py={1}>
            {avatars([
              [team2, "Romina Hadid"],
              [team4, "Jessica Doe"],
            ])}
          </SoftBox>
        ),
        ميزانية: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $3,000
          </SoftTypography>
        ),
        إكمال: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={10} color="info" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        المشروع: [logoSlack, "إصلاح أخطاء النظام الأساسي"],
        أعضاء: (
          <SoftBox display="flex" py={1}>
            {avatars([
              [team1, "Ryan Tompson"],
              [team3, "Alexander Smith"],
            ])}
          </SoftBox>
        ),
        ميزانية: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            Not set
          </SoftTypography>
        ),
        إكمال: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={100} color="success" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        المشروع: [logoSpotify, "إطلاق تطبيق الهاتف المحمول الخاص بنا"],
        أعضاء: (
          <SoftBox display="flex" py={1}>
            {avatars([
              [team4, "Jessica Doe"],
              [team3, "Alexander Smith"],
              [team2, "Romina Hadid"],
              [team1, "Ryan Tompson"],
            ])}
          </SoftBox>
        ),
        ميزانية: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $20,500
          </SoftTypography>
        ),
        إكمال: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={100} color="success" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        المشروع: [logoJira, "أضف صفحة التسعير الجديدة"],
        أعضاء: (
          <SoftBox display="flex" py={1}>
            {avatars([[team4, "Jessica Doe"]])}
          </SoftBox>
        ),
        ميزانية: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $500
          </SoftTypography>
        ),
        إكمال: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={25} color="info" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
      {
        المشروع: [logoInvesion, "إعادة تصميم متجر جديد على الإنترنت"],
        أعضاء: (
          <SoftBox display="flex" py={1}>
            {avatars([
              [team1, "Ryan Tompson"],
              [team4, "Jessica Doe"],
            ])}
          </SoftBox>
        ),
        ميزانية: (
          <SoftTypography variant="caption" color="text" fontWeight="medium">
            $2,000
          </SoftTypography>
        ),
        إكمال: (
          <SoftBox width="8rem" textAlign="left">
            <SoftProgress value={40} color="info" variant="gradient" label={false} />
          </SoftBox>
        ),
      },
    ],
  };
}
