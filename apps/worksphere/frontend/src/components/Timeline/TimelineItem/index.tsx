import { FC } from 'react';

// @mui material components
import { Icon } from '@mui/material';

// Custom components
import SoftBox from '../../SoftBox';
import SoftTypography from '../../SoftTypography';

interface TimelineItemProps {
  color?: 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'dark' | 'light';
  icon: string;
  title: string;
  dateTime: string;
  lastItem?: boolean;
}

const TimelineItem: FC<TimelineItemProps> = ({ color = "info", icon, title, dateTime, lastItem = false }) => {
  return (
    <SoftBox position="relative" mb={lastItem ? 0 : 3} sx={(theme) => ({
      '&:after': {
        content: lastItem ? 'none' : '""',
        position: 'absolute',
        left: '17px',
        top: '30px',
        height: lastItem ? 0 : 'calc(100% + 24px)',
        width: '2px',
        backgroundColor: theme.palette.grey[300],
      },
    })}>
      <SoftBox
        display="flex"
        justifyContent="center"
        alignItems="center"
        bgColor={color}
        color="white"
        width="35px"
        height="35px"
        borderRadius="50%"
        position="absolute"
        top="0"
        left="0"
        zIndex={2}
        sx={{
          fontSize: ({ typography: { size } }) => size.sm,
        }}
      >
        <Icon fontSize="inherit">{icon}</Icon>
      </SoftBox>
      <SoftBox ml={5.75} pt={0.5} lineHeight={0} maxWidth="30rem">
        <SoftTypography variant="button" fontWeight="medium" color={color}>
          {title}
        </SoftTypography>
        <SoftBox mt={0.5}>
          <SoftTypography variant="caption" color="text">
            {dateTime}
          </SoftTypography>
        </SoftBox>
      </SoftBox>
    </SoftBox>
  );
};

export default TimelineItem; 